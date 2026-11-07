"""One bounded HTTP transport for the supported stdio server.

Only status codes reach MCP errors. Response bodies, URLs and authorization headers
are deliberately excluded from exceptions. Mutations are sent exactly once.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from request_safety import PROCESS_GUARD, SafetyLimit, encode_payload


class ApiError(OSError):
    def __init__(self, status: int | None, code: str | None = None):
        self.status = status
        self.code = code
        message = ('plan_workout_start: Для старта по плану нужен доступ уровня Плюс.'
                   if code == 'plan_workout_start' else
                   'subscription_required: Для доступа к API нужна действующая подписка.'
                   if code == 'subscription_required' else
                   f'GymAssistant API: HTTP {status}.' if status else 'GymAssistant API недоступен.')
        super().__init__(message)


class InvalidResponse(ValueError):
    """The request may have succeeded; response content is unusable."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a PAT to a URL supplied by an API response."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class ApiTransport:
    def __init__(self, api_url: str, token: str | Callable[[], str]):
        parsed = urllib.parse.urlsplit(api_url)
        if (parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or
                parsed.password or parsed.query or parsed.fragment):
            raise ValueError('GYM_API_URL должен быть абсолютным HTTP(S) адресом без учётных данных.')
        if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Удалённый GymAssistant API должен использовать HTTPS.')
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.read_only = False
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, path: str, *, params=None, body=None, token=None, json_response=True):
        if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path:
            raise ValueError('Некорректный путь GymAssistant API.')
        if self.read_only and method.upper() != 'GET':
            raise SafetyLimit('MCP работает только на чтение; запрос записи не отправлен.')
        url = self.api_url + path
        if params:
            url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        credential = token or (self.token() if callable(self.token) else self.token)
        if not isinstance(credential, str) or len(credential) > 256 or any(
                ord(char) < 33 or ord(char) > 126 for char in credential):
            raise ValueError('GYM_API_TOKEN содержит недопустимые символы.')
        headers = {'Authorization': f'Bearer {credential}', 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = encode_payload(body)
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with PROCESS_GUARD.permit(method):
            return self._send(request, json_response)

    def _send(self, request, json_response):
        try:
            with self._opener.open(request, timeout=30) as response:
                if not json_response:
                    return {'status': 'ok'}
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise InvalidResponse('Ответ GymAssistant API слишком велик.')
                try:
                    return json.loads(raw) if raw else {'status': 'ok'}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise InvalidResponse('Некорректный ответ GymAssistant API.') from None
        except urllib.error.HTTPError as error:
            status = error.code
            if status in (429, 503):
                PROCESS_GUARD.cooldown(error.headers.get('Retry-After'))
            code = None
            if status in (401, 402, 403):
                try:
                    payload = json.loads(error.read(4096))
                    if isinstance(payload, dict):
                        if status == 403 and (payload.get('type') == 'plan_workout_start' or
                                              payload.get('feature') == 'plan_workout_start'):
                            code = 'plan_workout_start'
                        elif (payload.get('code') == 'subscription_required' or
                              payload.get('error') == 'subscription_required'):
                            code = 'subscription_required'
                except (ValueError, UnicodeDecodeError):
                    pass
            error.close()
            raise ApiError(status, code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise ApiError(None) from None

    def get(self, path: str, params=None, token=None):
        return self.request('GET', path, params=params, token=token)

    def write(self, method: str, path: str, body=None, *, json_response=True):
        """One attempt; callers must treat 5xx/disconnect as an unknown outcome."""
        return self.request(method, path, body=body, json_response=json_response)
