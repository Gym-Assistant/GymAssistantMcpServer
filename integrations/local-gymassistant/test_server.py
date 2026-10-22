"""Конфигурация и состав локального сервера: временные файлы, без сети и личных путей."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server

EXPECTED_TOOLS = {
    'gym_me', 'gym_workouts', 'gym_workout', 'gym_records', 'gym_body_latest',
    'gym_body_history', 'gym_status', 'gym_health_daily', 'gym_health_metrics',
    'gym_plans', 'gym_plan', 'gym_exercises', 'gym_create_plan', 'gym_append_plan_days',
}


class EnvFileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.here = self.root / 'server'
        self.config_home = self.root / 'config'
        self.here.mkdir()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_explicit_file_wins_and_process_env_overrides_values(self):
        explicit = self.write(self.root / 'custom' / 'secrets.env',
                              '# comment\nGYM_API_TOKEN="gma_from_file"\nGYM_API_URL=\'http://127.0.0.1:1/api\'\nbroken line\n')
        self.write(self.here / '.env', 'GYM_API_TOKEN=gma_local\n')
        config = server.load_config({'GYM_MCP_ENV_FILE': str(explicit), 'GYM_API_URL': 'http://127.0.0.1:2/api',
                                     'XDG_CONFIG_HOME': str(self.config_home)}, self.here)
        self.assertEqual(config['GYM_API_TOKEN'], 'gma_from_file')
        self.assertEqual(config['GYM_API_URL'], 'http://127.0.0.1:2/api')
        self.assertNotIn('broken line', config)

    def test_explicit_missing_file_is_an_error(self):
        with self.assertRaises(SystemExit) as caught:
            server.load_config({'GYM_MCP_ENV_FILE': str(self.root / 'missing.env')}, self.here)
        self.assertIn('GYM_MCP_ENV_FILE', str(caught.exception))

    def test_default_order_is_server_dir_then_xdg_config(self):
        environ = {'XDG_CONFIG_HOME': str(self.config_home)}
        xdg = self.write(self.config_home / 'gymassistant-mcp' / '.env', 'GYM_API_TOKEN=gma_xdg\n')
        self.assertEqual(server.find_env_file(environ, self.here), xdg)
        self.assertEqual(server.load_config(environ, self.here)['GYM_API_TOKEN'], 'gma_xdg')
        local = self.write(self.here / '.env', 'GYM_API_TOKEN=gma_local\n')
        self.assertEqual(server.find_env_file(environ, self.here), local)
        self.assertEqual(server.load_config(environ, self.here)['GYM_API_TOKEN'], 'gma_local')

    def test_without_file_only_process_environment_is_used(self):
        environ = {'XDG_CONFIG_HOME': str(self.config_home), 'GYM_API_TOKEN': 'gma_env'}
        self.assertIsNone(server.find_env_file(environ, self.here))
        self.assertEqual(server.load_config(environ, self.here), environ)

    def test_default_candidates_contain_no_personal_locations(self):
        candidates, explicit = server.env_file_candidates({'XDG_CONFIG_HOME': '/xdg'}, Path('/srv/mcp'))
        self.assertFalse(explicit)
        self.assertEqual(candidates, [Path('/srv/mcp/.env'), Path('/xdg/gymassistant-mcp/.env')])


class BuildServerTests(unittest.TestCase):
    def test_missing_token_stops_startup(self):
        with self.assertRaises(SystemExit):
            server.build_server({'GYM_API_URL': 'http://127.0.0.1:1/api'})

    def test_registers_all_fourteen_tools(self):
        mcp = server.build_server({'GYM_API_TOKEN': 'gma_fixture', 'GYM_API_URL': 'http://127.0.0.1:1/api/'})
        names = {tool.name for tool in asyncio.run(mcp.list_tools())}
        self.assertEqual(names, EXPECTED_TOOLS)

    def health_server(self, owners):
        calls = []

        def fake_factory(api_url, token):
            self.assertEqual(api_url, 'http://127.0.0.1:1/api')
            def get(path, params=None, override=None):
                used = override or token
                calls.append((path, used))
                return {'id': owners[used]} if path == '/auth/me' else {'metrics': []}
            return get

        with patch.object(server, 'make_api_get', fake_factory):
            mcp = server.build_server({'GYM_API_TOKEN': 'gma_main', 'GYM_HEALTH_API_TOKEN': 'gma_health',
                                       'GYM_API_URL': 'http://127.0.0.1:1/api'})
        return mcp, calls

    def test_separate_health_token_reads_only_same_account(self):
        mcp, calls = self.health_server({'gma_main': 'owner', 'gma_health': 'owner'})
        asyncio.run(mcp.call_tool('gym_health_metrics', {}))
        self.assertEqual(calls, [('/auth/me', 'gma_main'), ('/auth/me', 'gma_health'),
                                 ('/health/apple/metrics', 'gma_health')])

    def test_separate_health_token_of_other_account_is_refused(self):
        mcp, calls = self.health_server({'gma_main': 'owner', 'gma_health': 'other'})
        with self.assertRaisesRegex(Exception, 'разным аккаунтам'):
            asyncio.run(mcp.call_tool('gym_health_metrics', {}))
        self.assertEqual(calls, [('/auth/me', 'gma_main'), ('/auth/me', 'gma_health')])

if __name__ == '__main__':
    unittest.main()
