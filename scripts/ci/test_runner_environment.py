#!/usr/bin/env python3
"""Exercise runner isolation without touching Docker, credentials or production."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("prepare-runner.sh")


class RunnerIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ga-runner-guard-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.github_env = self.path / "github-env"
        self.github_env.touch()
        fake_bin = self.path / "bin"
        fake_bin.mkdir()
        docker = fake_bin / "docker"
        docker.write_text("""#!/bin/sh
printf '%s\\n' "${DOCKER_CONFIG:-unset}" >> "$FAKE_DOCKER_CALLS"
case "$1" in
  context) printf '%s\\n' "$FAKE_DOCKER_HOST" ;;
  version) printf '%s\\n' "$FAKE_DOCKER_OS" ;;
  *) exit 90 ;;
esac
""")
        docker.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "GA_RUNNER_MODE": "local",
            "GA_REPOSITORY_PRIVATE": "true",
            "GA_ACTOR": "trusted-owner",
            "GA_EVENT_NAME": "pull_request",
            "GA_HEAD_REPOSITORY": "Gym-Assistant/GymAssistantMcpServer",
            "GITHUB_REPOSITORY": "Gym-Assistant/GymAssistantMcpServer",
            "RUNNER_OS": "macOS",
            "RUNNER_ARCH": "ARM64",
            "RUNNER_TEMP": str(self.path),
            "GITHUB_ENV": str(self.github_env),
            "GA_PREPARE_DOCKER": "false",
            "FAKE_DOCKER_HOST": "unix:///local-test/docker.sock",
            "FAKE_DOCKER_OS": "linux",
            "FAKE_DOCKER_CALLS": str(self.path / "docker-calls"),
        }
        self.env.pop("DOCKER_HOST", None)

    def run_script(self, **overrides):
        return subprocess.run(
            ["bash", str(SCRIPT)], env={**self.env, **overrides},
            capture_output=True, text=True, check=False,
        )

    def test_trusted_local_event_without_docker_needs_no_daemon(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.github_env.read_text(), "")
        self.assertFalse((self.path / "docker-calls").exists())

    def test_public_repository_is_rejected_before_docker(self):
        result = self.run_script(GA_REPOSITORY_PRIVATE="false", GA_PREPARE_DOCKER="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.path / "docker-calls").exists())

    def test_fork_is_rejected(self):
        self.assertNotEqual(self.run_script(GA_HEAD_REPOSITORY="stranger/fork").returncode, 0)

    def test_dependabot_is_rejected(self):
        self.assertNotEqual(self.run_script(GA_ACTOR="dependabot[bot]").returncode, 0)

    def test_wrong_local_platform_is_rejected(self):
        self.assertNotEqual(self.run_script(RUNNER_OS="Linux").returncode, 0)
        self.assertNotEqual(self.run_script(RUNNER_ARCH="X64").returncode, 0)

    def test_hosted_mode_keeps_linux_supported(self):
        self.assertEqual(self.run_script(GA_RUNNER_MODE="", RUNNER_OS="Linux", RUNNER_ARCH="X64").returncode, 0)

    def test_docker_uses_new_private_config_and_original_context(self):
        result = self.run_script(GA_PREPARE_DOCKER="true", DOCKER_CONFIG="/private-original-config")
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = dict(line.split("=", 1) for line in self.github_env.read_text().splitlines())
        self.assertEqual(entries["DOCKER_HOST"], "unix:///local-test/docker.sock")
        config = Path(entries["DOCKER_CONFIG"])
        self.assertEqual(config.parent, self.path)
        self.assertEqual(config.stat().st_mode & 0o777, 0o700)
        self.assertEqual((config / "config.json").stat().st_mode & 0o777, 0o600)
        self.assertLessEqual(set(json.loads((config / "config.json").read_text())), {"cliPluginsExtraDirs"})
        self.assertEqual((self.path / "docker-calls").read_text().splitlines(), ["/private-original-config"] * 2)

    def test_remote_docker_is_rejected_without_creating_config(self):
        result = self.run_script(GA_PREPARE_DOCKER="true", FAKE_DOCKER_HOST="tcp://remote:2375")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_env.read_text(), "")

    def test_multiline_docker_host_cannot_inject_environment(self):
        result = self.run_script(GA_PREPARE_DOCKER="true", FAKE_DOCKER_HOST="unix:///socket\nINJECTED=value")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_env.read_text(), "")

    def test_non_linux_daemon_is_rejected(self):
        result = self.run_script(GA_PREPARE_DOCKER="true", FAKE_DOCKER_OS="windows")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.github_env.read_text(), "")


if __name__ == "__main__":
    unittest.main()
