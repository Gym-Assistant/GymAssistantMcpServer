"""Установщик: резервная копия, неизменность .env/.venv/run.sh, без личных путей."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.environ = {'XDG_CONFIG_HOME': str(self.root / 'config')}

    def run_install(self, target, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            backup = install.install(target, environ=self.environ, **kwargs)
        return backup, output.getvalue()

    def test_fresh_install_copies_modules_and_wrapper(self):
        target = self.root / 'fresh'
        backup, output = self.run_install(target)
        for name in install.MANAGED:
            self.assertEqual((target / name).read_bytes(), (install.SOURCE / name).read_bytes())
        self.assertTrue((target / 'run.sh').stat().st_mode & 0o111)
        self.assertFalse(backup.exists())
        self.assertIn('python3 -m venv', output)
        self.assertIn('GYM_MCP_ENV_FILE', output)

    def test_existing_install_is_backed_up_and_private_files_untouched(self):
        target = self.root / 'live'
        (target / '.venv' / 'bin').mkdir(parents=True)
        (target / '.venv' / 'bin' / 'python').write_text('')
        (target / 'server.py').write_text('# old server\n')
        (target / 'health_tools.py').write_text('# old health\n')
        wrapper = '#!/bin/sh\nexport GYM_MCP_ENV_FILE="/fixture/.env"\nexec ./.venv/bin/python server.py\n'
        (target / 'run.sh').write_text(wrapper)
        (target / '.env').write_text('GYM_API_TOKEN=gma_fixture\n')
        backup, output = self.run_install(target)
        self.assertEqual((backup / 'server.py').read_text(), '# old server\n')
        self.assertEqual((backup / 'health_tools.py').read_text(), '# old health\n')
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual((target / 'run.sh').read_text(), wrapper)
        self.assertEqual((target / '.env').read_text(), 'GYM_API_TOKEN=gma_fixture\n')
        self.assertEqual((target / 'server.py').read_bytes(), (install.SOURCE / 'server.py').read_bytes())
        self.assertIn('Откат', output)
        self.assertIn('core_tools.py', output)  # новый файл: удалить при откате
        self.assertNotIn('Внимание', output)

    def test_dry_run_changes_nothing(self):
        target = self.root / 'dry'
        target.mkdir()
        (target / 'server.py').write_text('# old server\n')
        _, output = self.run_install(target, dry_run=True)
        self.assertEqual(sorted(p.name for p in target.iterdir()), ['server.py'])
        self.assertIn('server.py', output)

    def test_refuses_to_install_over_sources(self):
        with self.assertRaises(ValueError):
            install.install(install.SOURCE, environ=self.environ)

    def test_wrapper_detection_ignores_comments(self):
        self.assertFalse(install.wrapper_sets_env_file('# export GYM_MCP_ENV_FILE="/x"\n'))
        self.assertTrue(install.wrapper_sets_env_file('  export GYM_MCP_ENV_FILE="/x"\n'))


if __name__ == '__main__':
    unittest.main()
