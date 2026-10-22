"""Проверка контракта Health-инструмента без личных данных и сети."""
import unittest
from health_tools import register_health_tools, same_account_reader


class Registry:
    def __init__(self):
        self.functions = {}
        self.annotations = {}

    def tool(self, **kwargs):
        def register(fn):
            self.functions[fn.__name__] = fn
            self.annotations[fn.__name__] = kwargs['annotations']
            return fn
        return register

    def call(self, *args):
        return self.functions['gym_health_daily'](*args)


class HealthToolsTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.calls = []
        self.data = [{'snapshot': {'day': '2026-10-17', 'values': {'steps': 23, 'protein': None}}, 'receivedAt': '2026-10-17T12:00:00Z'}]
        def get(path, params=None):
            self.calls.append((path, params))
            return self.data
        register_health_tools(self.registry, get)

    def test_preserves_response_and_freshness(self):
        result = self.registry.call('2026-09-17', '2026-10-17')
        self.assertIs(result, self.data)
        self.assertEqual(self.calls, [('/health/apple/daily', {'from': '2026-09-17', 'to': '2026-10-17'})])
        self.assertTrue(self.registry.annotations['gym_health_daily'].readOnlyHint)
        self.assertFalse(self.registry.annotations['gym_health_daily'].destructiveHint)

    def test_metric_catalog_is_forwarded_read_only(self):
        catalog = {'metrics': [{'key': 'steps', 'unit': 'count', 'aggregation': 'sum'}]}
        self.data = catalog
        self.assertIs(self.registry.functions['gym_health_metrics'](), catalog)
        self.assertEqual(self.calls, [('/health/apple/metrics', None)])
        self.assertTrue(self.registry.annotations['gym_health_metrics'].readOnlyHint)
        self.assertEqual(set(self.registry.functions), {'gym_health_daily', 'gym_health_metrics'})

    def test_invalid_period_does_not_call_api(self):
        for start, end in [('2026-09-16', '2026-10-17'), ('2026-10-18', '2026-10-17'), ('20261017', '2026-10-17'), ('2026-02-30', '2026-10-17')]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.registry.call(start, end)
        self.assertEqual(self.calls, [])

    def test_empty_data_remains_empty(self):
        self.data.clear()
        self.assertEqual(self.registry.call('2026-10-17', '2026-10-17'), [])


class AccountBoundaryTests(unittest.TestCase):
    def test_different_owners_do_not_read_health(self):
        calls = []
        def health_get(path, params=None):
            calls.append(path)
            return {'id': 'other'}
        reader = same_account_reader(lambda path: {'id': 'owner'}, health_get)
        with self.assertRaises(ValueError):
            reader('/health/apple/daily', {})
        self.assertEqual(calls, ['/auth/me'])

    def test_matching_owners_use_scoped_token(self):
        result = [{'snapshot': {'values': {'protein': None}}}]
        reader = same_account_reader(lambda path: {'id': 'owner'},
            lambda path, params=None: {'id': 'owner'} if path == '/auth/me' else result)
        self.assertIs(reader('/health/apple/daily', {}), result)


if __name__ == '__main__':
    unittest.main()
