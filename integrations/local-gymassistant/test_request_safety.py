"""Safety boundaries use fake time/network: no production load tests."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
from threading import Event
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from http_transport import ApiError, ApiTransport
from request_safety import RequestGuard, SafetyLimit, SafeFastMCP, encode_payload
import server


class RequestSafetyTests(unittest.TestCase):
    def test_shared_limit_covers_new_transport_and_token_override(self):
        now = [0.0]
        guard = RequestGuard(clock=lambda: now[0])
        @contextmanager
        def response(*args, **kwargs):
            yield BytesIO(b'{}')
        with patch('http_transport.PROCESS_GUARD', guard):
            for i in range(120):
                api = ApiTransport('http://localhost/api', 'gma_a')
                api._opener.open = response
                api.get('/plans', token='gma_b')
            api._opener.open = Mock(side_effect=AssertionError('must not send'))
            with self.assertRaises(SafetyLimit):
                api.get('/plans')
            now[0] = 60
            api._opener.open = response
            self.assertEqual(api.get('/plans'), {})

    def test_parallel_slots_and_exception_release(self):
        guard = RequestGuard()
        entered = [Event(), Event()]
        release = Event()
        def hold(index):
            with guard.permit('GET'):
                entered[index].set()
                release.wait(5)
                raise RuntimeError('network failed')
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(hold, i) for i in range(2)]
            try:
                self.assertTrue(all(e.wait(2) for e in entered))
                with self.assertRaises(SafetyLimit):
                    with guard.permit('GET'): pass
            finally:
                release.set()
            for future in futures:
                with self.assertRaises(RuntimeError): future.result()
        with guard.permit('GET'): pass
        self.assertEqual(guard.active, 0)

    def test_write_limit_and_cooldown_no_retry(self):
        now = [0.0]
        guard = RequestGuard(clock=lambda: now[0])
        for _ in range(12):
            with guard.permit('POST'): pass
        with self.assertRaises(SafetyLimit):
            with guard.permit('DELETE'): pass
        now[0] = 60
        api = ApiTransport('http://localhost/api', 'gma_a')
        api._opener.open = Mock(side_effect=HTTPError('private', 429, 'private', {'Retry-After': '90'}, BytesIO()))
        with patch('http_transport.PROCESS_GUARD', guard):
            with self.assertRaises(ApiError): api.get('/plans')
            with self.assertRaises(SafetyLimit): api.get('/plans')
        self.assertEqual(api._opener.open.call_count, 1)
        self.assertEqual(guard.cooldown_until, 150)

    def test_tool_budget_covers_fanout_and_does_not_leak_to_next_call(self):
        mcp = SafeFastMCP('synthetic')
        api = ApiTransport('http://localhost/api', 'gma_a')
        @contextmanager
        def response(*args, **kwargs): yield BytesIO(b'{}')
        api._opener.open = Mock(side_effect=response)
        @mcp.tool()
        def many():
            for _ in range(65): api.get('/plans')
        @mcp.tool()
        def one(): return api.get('/plans')
        async def run():
            with self.assertRaisesRegex(Exception, 'один вызов'): await mcp.call_tool('many', {})
            await mcp.call_tool('one', {})
        with patch('http_transport.PROCESS_GUARD', RequestGuard()): asyncio.run(run())
        self.assertEqual(api._opener.open.call_count, 65)

    def test_read_only_rejects_plan_before_reads_backup_or_network(self):
        mcp = server.build_server({'GYM_API_TOKEN': 'gma_a', 'GYM_MCP_READ_ONLY': '1'})
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(SafetyLimit, 'чтение'):
                asyncio.run(mcp.call_tool('gym_create_plan', {'name': 'test', 'days': []}))
        api = ApiTransport('http://localhost/api', 'gma_a'); api.read_only = True
        with self.assertRaises(SafetyLimit): api.write('POST', '/plans', {})

    def test_payload_bounds_before_network(self):
        api = ApiTransport('http://localhost/api', 'gma_a')
        api._opener.open = Mock(side_effect=AssertionError('network'))
        nested = {}
        for _ in range(22): nested = {'x': nested}
        for body in ({'text': 'я' * 10001}, nested, {'rows': ['я' * 9000] * 60}):
            with self.assertRaises(SafetyLimit): api.write('POST', '/plans', body)
        self.assertEqual(api._opener.open.call_count, 0)
        self.assertEqual(encode_payload({'name': 'План'}).decode(), '{"name": "План"}')

    def test_never_ending_catalog_stops_before_plan_write(self):
        from plan_tools import register_plan_tools
        from test_plan_tools import Registry, day, PERSONAL
        registry = Registry()
        get = Mock(return_value={'items': [{'id': PERSONAL, 'name': 'synthetic'}] * 100, 'total': 999999})
        post = Mock(side_effect=AssertionError('must not write'))
        register_plan_tools(registry, get, post)
        with self.assertRaises(SafetyLimit):
            registry.functions['gym_create_plan']('test', [day()])
        self.assertEqual(get.call_count, 50)
        post.assert_not_called()

    def test_backup_rejects_payload_or_full_directory_without_new_file(self):
        import os
        import tempfile
        from pathlib import Path
        from plan_tools import _backup_plan
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GYM_PLAN_BACKUP_DIR': directory}):
            with self.assertRaises(SafetyLimit): _backup_plan({'id': 'synthetic'}, {'text': 'x' * 10001})
            self.assertEqual(list(Path(directory).iterdir()), [])
            old = Path(directory) / 'plan-old.json'
            with old.open('wb') as stream: stream.truncate(100 * 1024 * 1024)
            with self.assertRaises(SafetyLimit): _backup_plan({'id': 'synthetic'}, {})
            self.assertEqual(list(Path(directory).iterdir()), [old])

    def test_remote_auth_fresh_transport_cannot_bypass_process_limit(self):
        import httpx
        from remote_http import build_http_app
        guard = RequestGuard()
        for _ in range(120):
            with guard.permit('GET'): pass
        app = build_http_app({'GYM_API_URL': 'http://127.0.0.1:1/api'})
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
                response = await client.post('/mcp', headers={'Authorization': 'Bearer gma_fixture'})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.json()['code'], 'mcp_rate_limited')
        with patch('http_transport.PROCESS_GUARD', guard): asyncio.run(run())

    def test_core_pagination_bounds_are_explicit_not_partial(self):
        from core_tools import register_core_tools
        from test_plan_tools import PERSONAL
        class Registry:
            def __init__(self): self.functions = {}
            def tool(self, **kwargs):
                def register(fn):
                    self.functions[fn.__name__] = fn
                    return fn
                return register
        for name in ('gym_status', 'gym_body_latest'):
            registry = Registry()
            def get(path, params=None):
                if path == '/auth/me': return {'id': PERSONAL}
                return {'items': [{'id': PERSONAL, 'name': 'synthetic'}] * 200}
            calls = Mock(side_effect=get)
            register_core_tools(registry, calls, 'synthetic')
            with self.assertRaises(SafetyLimit): registry.functions[name]()
            self.assertEqual(calls.call_count, 51)

    def test_http_date_retry_after_is_honored_and_bounded(self):
        from email.utils import formatdate
        guard = RequestGuard(clock=lambda: 10, wall_clock=lambda: 1700000000)
        guard.cooldown(formatdate(1700000120, usegmt=True))
        self.assertEqual(guard.cooldown_until, 130)
        guard.cooldown(formatdate(1700001000, usegmt=True))
        self.assertEqual(guard.cooldown_until, 310)
