"""Tests for plugin loader safety checks.

The mode/ownership checks are POSIX-only (skipped on Windows).
"""

import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.plugin_manager import _check_plugin_file_safety, PluginBase, PluginManager


@unittest.skipIf(sys.platform == "win32", "POSIX permission checks N/A on Windows")
class TestCheckPluginFileSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "plugin.py")
        with open(self.path, "w") as f:
            f.write("# fake plugin\n")
        os.chmod(self.path, 0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_normal_file_owned_by_us_passes(self):
        # Default: file owned by current uid, mode 0600 → safe
        self.assertIsNone(_check_plugin_file_safety(self.path))

    def test_world_writable_refused(self):
        os.chmod(self.path, 0o666)
        problem = _check_plugin_file_safety(self.path)
        self.assertIsNotNone(problem)
        self.assertIn("world-writable", problem)

    def test_missing_file_returns_reason(self):
        problem = _check_plugin_file_safety("/no/such/path.py")
        self.assertIsNotNone(problem)
        self.assertIn("could not stat", problem)

    @patch("os.stat")
    def test_wrong_owner_refused(self, mock_stat):
        # Forge st_uid to a third user (not 0, not our euid)
        my_euid = os.geteuid()
        forged_uid = (my_euid + 1) if my_euid != 0 else 99999
        mock_stat.return_value = os.stat_result(
            (0o100600, 0, 0, 1, forged_uid, 0, 100, 0, 0, 0)
        )
        problem = _check_plugin_file_safety(self.path)
        self.assertIsNotNone(problem)
        self.assertIn(f"uid {forged_uid}", problem)

    @patch("os.stat")
    def test_root_owned_passes(self, mock_stat):
        mock_stat.return_value = os.stat_result(
            (0o100600, 0, 0, 1, 0, 0, 100, 0, 0, 0)  # uid=0 = root
        )
        self.assertIsNone(_check_plugin_file_safety(self.path))


class TestCheckPluginFileSafetyOnWindows(unittest.TestCase):
    """On Windows the check is a no-op (returns None)."""

    @unittest.skipUnless(sys.platform == "win32", "Windows-only smoke")
    def test_windows_returns_none(self):
        # Use an existing path so the function doesn't bail on stat()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            self.assertIsNone(_check_plugin_file_safety(path))
        finally:
            os.unlink(path)


class _FakePlugin(PluginBase):
    """Bare-bones PluginBase subclass for credentials_allowed() tests."""
    def run(self, scan_id, hosts, scan_results):
        return {'vulnerabilities': 0}


class TestCredentialsAllowedGate(unittest.TestCase):
    """The credentials_allowed() gate defaults to False; explicit opt-in only.

    Any plugin doing brute-force / weak-cred testing MUST honor this.
    """
    def test_default_is_false(self):
        plugin = _FakePlugin({'name': 'fake'})
        self.assertFalse(plugin.credentials_allowed())

    def test_flag_set_true(self):
        plugin = _FakePlugin({'name': 'fake'})
        plugin._allow_credential_attempts = True
        self.assertTrue(plugin.credentials_allowed())

    def test_flag_set_false(self):
        plugin = _FakePlugin({'name': 'fake'})
        plugin._allow_credential_attempts = False
        self.assertFalse(plugin.credentials_allowed())


class TestPluginManagerReadsSafetyConfig(unittest.TestCase):
    """PluginManager exposes safety.plugins.allow_credential_attempts."""
    def _make(self, safety_cfg):
        cfg = {
            'plugins': {'enabled': False, 'directory': '/tmp', 'auto_load': False},
            'safety': safety_cfg,
        }
        return PluginManager(cfg, database=None)

    def test_default_off(self):
        pm = self._make({})
        self.assertFalse(pm.allow_credential_attempts)

    def test_explicit_off(self):
        pm = self._make({'plugins': {'allow_credential_attempts': False}})
        self.assertFalse(pm.allow_credential_attempts)

    def test_explicit_on(self):
        pm = self._make({'plugins': {'allow_credential_attempts': True}})
        self.assertTrue(pm.allow_credential_attempts)

    def test_safety_section_missing(self):
        # No safety key at all → gate stays off (fail-safe)
        cfg = {'plugins': {'enabled': False, 'directory': '/tmp', 'auto_load': False}}
        pm = PluginManager(cfg, database=None)
        self.assertFalse(pm.allow_credential_attempts)


if __name__ == "__main__":
    unittest.main()
