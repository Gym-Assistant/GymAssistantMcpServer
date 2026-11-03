"""Prepared Streamable HTTP adapter around the same tool registry as stdio.

This adapter is loopback only by default and is not wired into production. Every
HTTP request verifies the user's PAT with the backend; no service-wide PAT exists.
Stateless MCP sessions avoid carrying one user's session into another request.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
import os
from urllib.parse import urlsplit
from uuid import UUID

from http_transport import ApiError, ApiTransport
from request_safety import SafetyLimit


_bearer: ContextVar[str | None] = ContextVar('gym_mcp_http_bearer', default=None)


def current_bearer() -> str:
    token = _bearer.get()
    if token is None:
        raise ValueError('HTTP-запрос не аутентифицирован.')
    return token


class UserPatMiddleware:
    def __init__(self, app, api_url: str):
        self.app = app
        self.api_url = api_url

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        authorization = [value for key, value in scope.get('headers', []) if key.lower() == b'authorization']
        raw = authorization[0] if len(authorization) == 1 else b''
        if not raw.startswith(b'Bearer ') or len(raw) > 256:
            await _json_error(send, 401, 'invalid_token', 'Нужен личный API-токен GymAssistant.')
            return
        try:
            token = raw[7:].decode('ascii')
        except UnicodeDecodeError:
            await _json_error(send, 401, 'invalid_token', 'Нужен личный API-токен GymAssistant.')
            return
        if not token.startswith('gma_') or any(ch.isspace() for ch in token):
            await _json_error(send, 401, 'invalid_token', 'Нужен личный API-токен GymAssistant.')
            return
        try:
            me = await asyncio.to_thread(ApiTransport(self.api_url, token).get, '/auth/me')
            UUID(str(me['id']))
        except SafetyLimit:
            await _json_error(send, 429, 'mcp_rate_limited', 'Лимит MCP достигнут. Повторите позже.')
            return
        except ApiError as error:
            if error.code == 'subscription_required':
                await _json_error(send, 403, error.code, 'Для доступа к API нужна действующая подписка.')
            elif error.status == 403:
                await _json_error(send, 403, 'insufficient_scope', 'Нужно право profile:read.')
            else:
                await _json_error(send, 401 if error.status == 401 else 503,
                                  'invalid_token' if error.status == 401 else 'backend_unavailable',
                                  'Токен не принят.' if error.status == 401 else 'API временно недоступен.')
            return
        except (KeyError, ValueError, TypeError):
            await _json_error(send, 503, 'backend_unavailable', 'API временно недоступен.')
            return
        marker = _bearer.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _bearer.reset(marker)


async def _json_error(send, status, code, message):
    body = json.dumps({'code': code, 'message': message}, ensure_ascii=False).encode('utf-8')
    headers = [(b'content-type', b'application/json; charset=utf-8'),
               (b'content-length', str(len(body)).encode()),
               (b'cache-control', b'no-store')]
    if status == 429:
        headers.append((b'retry-after', b'60'))
    if status in (401, 403):
        challenge = ('Bearer error="insufficient_scope", error_description="subscription_required"'
                     if code == 'subscription_required' else
                     'Bearer error="insufficient_scope"' if status == 403 else
                     'Bearer error="invalid_token"')
        headers.append((b'www-authenticate', challenge.encode('ascii')))
    await send({'type': 'http.response.start', 'status': status,
                'headers': headers})
    await send({'type': 'http.response.body', 'body': body})


def build_http_app(config: dict):
    from server import build_server, DEFAULT_API_URL

    host = config.get('GYM_MCP_HTTP_BIND', '127.0.0.1')
    if host not in ('127.0.0.1', 'localhost', '::1'):
        public_url = config.get('GYM_MCP_PUBLIC_URL', '')
        parsed = urlsplit(public_url)
        if config.get('GYM_MCP_HTTP_ALLOW_NONLOCAL') != '1' or parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('Внешний bind требует явного разрешения и HTTPS-адреса reverse proxy.')
    if config.get('GYM_API_TOKEN') or config.get('GYM_HEALTH_API_TOKEN'):
        raise ValueError('Удалённый режим не использует общий API/Health-токен.')
    mcp = build_server(config, remote=True)
    return UserPatMiddleware(mcp.streamable_http_app(),
                             (config.get('GYM_API_URL') or DEFAULT_API_URL).rstrip('/'))


if __name__ == '__main__':
    import uvicorn
    from server import load_config

    settings = load_config()
    app = build_http_app(settings)
    uvicorn.run(app, host=settings.get('GYM_MCP_HTTP_BIND', '127.0.0.1'),
                port=int(settings.get('GYM_MCP_HTTP_PORT', '8765')),
                log_level='warning', access_log=False)
