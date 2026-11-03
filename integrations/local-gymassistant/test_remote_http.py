"""Isolated Streamable HTTP checks; no production network or real tokens."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from uuid import uuid4

import httpx

from remote_http import build_http_app


class RemoteFixture:
    def __init__(self):
        self.users = {'gma_owner_a': str(uuid4()), 'gma_owner_b': str(uuid4()),
                      'gma_expired_plan': str(uuid4()), 'gma_limited': str(uuid4()),
                      'gma_no_profile': str(uuid4())}
        self.entitled = False
        self.calls = []

    def handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                fixture.calls.append((token, self.path))
                if token not in fixture.users:
                    status, body = 401, {'error': 'private backend detail'}
                elif token == 'gma_expired_plan' and not fixture.entitled:
                    status, body = 403, {'error': 'subscription_required', 'message': 'private backend detail'}
                elif token == 'gma_no_profile' and self.path == '/api/auth/me':
                    status, body = 403, {'error': 'private scope detail'}
                elif self.path == '/api/auth/me':
                    status, body = 200, {'id': fixture.users[token]}
                elif self.path.startswith('/api/plans?') and token == 'gma_limited':
                    status, body = 403, {'error': 'private scope detail'}
                elif self.path.startswith('/api/plans?'):
                    status, body = 200, {'items': [{'id': fixture.users[token], 'authorUserId': fixture.users[token],
                                                    'name': 'synthetic'}], 'total': 1}
                elif self.path.startswith('/api/exercises?'):
                    ids = ([str(uuid4()), str(uuid4())] if token == 'gma_owner_a' else
                           [str(uuid4())] if token == 'gma_owner_b' else [])
                    status, body = 200, {'items': [{'id': id_, 'name': 'synthetic'} for id_ in ids],
                                         'total': len(ids)}
                else:
                    status, body = 404, {}
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
           'MCP-Protocol-Version': '2025-06-18'}


def rpc(method, request_id, params=None):
    return {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params or {}}


class RemoteHttpTests(unittest.TestCase):
    def test_nonlocal_bind_requires_explicit_https_proxy(self):
        for config in ({'GYM_MCP_HTTP_BIND': '0.0.0.0'},
                       {'GYM_MCP_HTTP_BIND': '0.0.0.0', 'GYM_MCP_HTTP_ALLOW_NONLOCAL': '1',
                        'GYM_MCP_PUBLIC_URL': 'http://example.invalid/mcp'}):
            with self.assertRaises(ValueError):
                build_http_app(config)

    def test_two_users_expiry_and_renewal_share_no_credentials(self):
        fixture = RemoteFixture()
        backend = ThreadingHTTPServer(('127.0.0.1', 0), fixture.handler())
        thread = Thread(target=backend.serve_forever, daemon=True)
        thread.start()
        app = build_http_app({'GYM_API_URL': f'http://127.0.0.1:{backend.server_port}/api'})

        async def run():
            async with app.app.router.lifespan_context(app.app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url='http://127.0.0.1:8765') as client:
                    async def call(token, method='tools/call', params=None):
                        headers = {**HEADERS, 'Authorization': f'Bearer {token}'}
                        result = await client.post('/mcp', headers=headers,
                                                   json=rpc(method, len(fixture.calls) + 1, params))
                        return result.status_code, result.json()

                    bad_status, bad = await call('gma_invalid')
                    self.assertEqual((bad_status, bad['code']), (401, 'invalid_token'))
                    limited_status, no_profile = await call('gma_no_profile')
                    self.assertEqual((limited_status, no_profile['code']), (403, 'insufficient_scope'))
                    owners = ('gma_owner_a', 'gma_owner_b')
                    results = await asyncio.gather(*(call(token, params={'name': 'list_plans', 'arguments': {}})
                                                     for token in owners))
                    for token, (status, result) in zip(owners, results):
                        self.assertEqual(status, 200)
                        text = json.dumps(result)
                        self.assertIn(fixture.users[token], text)
                        other = 'gma_owner_b' if token == 'gma_owner_a' else 'gma_owner_a'
                        self.assertNotIn(fixture.users[other], text)

                    # One HTTP app serves both PATs. The second caller must not
                    # inherit the first caller's personal exercise cache.
                    for token, expected in (('gma_owner_a', 2), ('gma_owner_b', 1)):
                        status, result = await call(token, params={'name': 'gym_status', 'arguments': {}})
                        self.assertEqual(status, 200)
                        self.assertEqual(json.loads(result['result']['content'][0]['text'])
                                         ['exercises_in_catalog'], expected)

                    status, denied = await call('gma_expired_plan', params={'name': 'list_plans', 'arguments': {}})
                    self.assertEqual(status, 403)
                    denied_text = json.dumps(denied)
                    self.assertIn('subscription_required', denied_text)
                    self.assertNotIn(fixture.users['gma_expired_plan'], denied_text)
                    self.assertNotIn('private backend detail', denied_text)
                    challenge = await client.post('/mcp', headers={**HEADERS,
                                                  'Authorization': 'Bearer gma_expired_plan'},
                                                  json=rpc('tools/list', 99))
                    self.assertEqual(challenge.status_code, 403)
                    self.assertEqual(challenge.headers['www-authenticate'],
                                     'Bearer error="insufficient_scope", error_description="subscription_required"')
                    fixture.entitled = True
                    status, renewed = await call('gma_expired_plan', params={'name': 'list_plans', 'arguments': {}})
                    self.assertEqual(status, 200)
                    self.assertIn(fixture.users['gma_expired_plan'], json.dumps(renewed))

                    status, limited = await call('gma_limited', params={'name': 'list_plans', 'arguments': {}})
                    self.assertEqual(status, 200)
                    self.assertIn('HTTP 403', json.dumps(limited))
                    self.assertNotIn('private scope detail', json.dumps(limited))
        try:
            asyncio.run(run())
        finally:
            backend.shutdown()
            backend.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
