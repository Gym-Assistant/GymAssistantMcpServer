"""Security and compatibility checks for the single MCP runtime; synthetic only."""
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4
import unittest

from mcp.server.fastmcp import FastMCP

from compat_tools import COMPAT_TOOL_NAMES, register_compat_tools
from http_transport import ApiError, ApiTransport, InvalidResponse


OWNER = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.responses = {'/auth/me': {'id': OWNER}}
        self.write_error = None

    def get(self, path, params=None, token=None):
        self.calls.append(('GET', path, params))
        if path not in self.responses:
            raise ApiError(404)
        return self.responses[path]

    def write(self, method, path, body=None, json_response=True):
        self.calls.append((method, path, body))
        if self.write_error:
            raise self.write_error
        return {'status': 'ok'}

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {'status': 'ok'}


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.mcp = FastMCP('test')
        register_compat_tools(self.mcp, self.transport, self.transport.get)

    def call(self, name, args=None):
        return asyncio.run(self.mcp.call_tool(name, args or {}))

    def test_exact_legacy_name_set_is_registered(self):
        names = {tool.name for tool in asyncio.run(self.mcp.list_tools())}
        self.assertEqual(names, COMPAT_TOOL_NAMES)
        self.assertEqual(len(names), 44)

    def test_raw_legacy_write_is_disabled_before_http(self):
        with self.assertRaisesRegex(Exception, 'выключен'):
            self.call('create_plan', {'body': {'id': str(uuid4()), 'name': 'Fixture'}})
        self.assertEqual(self.transport.calls, [])

    def test_foreign_plan_and_workout_do_not_leak_content(self):
        plan_id, workout_id = str(uuid4()), str(uuid4())
        self.transport.responses['/plans/' + plan_id] = {'id': plan_id, 'authorUserId': OTHER,
                                                           'name': 'private title'}
        self.transport.responses['/workouts/' + workout_id] = {'id': workout_id,
                                                                 'createdById': OTHER, 'comment': 'private note'}
        for name, target, forbidden in [('get_plan', plan_id, 'private title'),
                                         ('get_workout', workout_id, 'private note')]:
            with self.assertRaises(Exception) as caught:
                self.call(name, {'id': target})
            self.assertNotIn(forbidden, str(caught.exception))

    def test_legacy_create_rejects_existing_id_without_write(self):
        transport = FakeTransport()
        mcp = FastMCP('test-writes')
        register_compat_tools(mcp, transport, transport.get, legacy_writes=True)
        plan_id = str(uuid4())
        transport.responses['/plans/' + plan_id] = {'id': plan_id, 'authorUserId': OWNER}
        with self.assertRaisesRegex(Exception, 'upsert запрещён'):
            asyncio.run(mcp.call_tool('create_plan', {'body': {'id': plan_id, 'name': 'Fixture'}}))
        self.assertFalse(any(call[0] != 'GET' for call in transport.calls))

    def test_write_5xx_is_unknown_and_not_retried(self):
        transport = FakeTransport()
        mcp = FastMCP('test-writes')
        register_compat_tools(mcp, transport, transport.get, legacy_writes=True)
        plan_id = str(uuid4())
        transport.write_error = ApiError(500)
        result = asyncio.run(mcp.call_tool('create_plan', {'body': {'id': plan_id, 'name': 'Fixture'}}))
        value = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        self.assertEqual(value['status'], 'unknown')
        self.assertEqual(value['id'], plan_id)
        self.assertEqual(sum(call[0] == 'POST' for call in transport.calls), 1)

    def test_health_alias_keeps_dotnet_from_to_parameters(self):
        self.transport.responses['/health/apple/daily'] = [{'snapshot': {'values': {'steps': None}}}]
        result = self.call('get_apple_health_daily', {'from': '2026-10-20', 'to': '2026-10-20'})
        value = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        self.assertIsNone(value['result'][0]['snapshot']['values']['steps'])
        self.assertIn(('GET', '/health/apple/daily', {'from': '2026-10-20', 'to': '2026-10-20'}),
                      self.transport.calls)

    def test_transport_rejects_insecure_remote_and_credentials(self):
        for url in ('http://example.com/api', 'https://user:pass@example.com/api'):
            with self.assertRaises(ValueError):
                ApiTransport(url, 'synthetic')

    def test_transport_does_not_forward_pat_on_redirect(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get('Authorization')))
                if self.path == '/api/auth/me':
                    self.send_response(302)
                    self.send_header('Location', '/capture')
                else:
                    self.send_response(200)
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = ApiTransport(f'http://127.0.0.1:{server.server_port}/api', 'gma_synthetic')
            with self.assertRaises(ApiError) as caught:
                api.get('/auth/me')
            self.assertEqual(caught.exception.status, 302)
            self.assertEqual(seen, [('/api/auth/me', 'Bearer gma_synthetic')])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_invalid_write_response_is_unknown(self):
        transport = FakeTransport()
        mcp = FastMCP('test-writes')
        register_compat_tools(mcp, transport, transport.get, legacy_writes=True)
        transport.write_error = InvalidResponse('sensitive raw body')
        result = asyncio.run(mcp.call_tool('create_plan', {'body': {'id': str(uuid4()), 'name': 'Fixture'}}))
        value = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        self.assertEqual(value['status'], 'unknown')
        self.assertNotIn('sensitive raw body', str(result))

    def test_expired_and_limited_tokens_redact_server_body(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                token = self.headers.get('Authorization')
                seen.append(token)
                status = 401 if token == 'Bearer gma_expired_synthetic' else 403
                payload = (b'{"error":"subscription_required","message":"private user@example.invalid"}'
                           if token == 'Bearer gma_subscription_synthetic' else
                           b'private server detail: user@example.invalid; bearer secret')
                self.send_response(status)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for token, status in [('gma_expired_synthetic', 401), ('gma_limited_synthetic', 403),
                                  ('gma_subscription_synthetic', 403)]:
                api = ApiTransport(f'http://127.0.0.1:{server.server_port}/api', token)
                with self.assertRaises(ApiError) as caught:
                    api.get('/auth/me')
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(caught.exception.code,
                                 'subscription_required' if token == 'gma_subscription_synthetic' else None)
                self.assertNotIn('user@example.invalid', str(caught.exception))
                self.assertNotIn(token, str(caught.exception))
            self.assertEqual(seen, ['Bearer gma_expired_synthetic', 'Bearer gma_limited_synthetic',
                                    'Bearer gma_subscription_synthetic'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
