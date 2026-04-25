"""Unit tests for core.safety — runs on Windows without root or hardware."""

import unittest
from unittest.mock import patch

from core.safety import (
    SafetyConfig,
    SafetyViolation,
    SSHGuard,
    preflight_check,
)


# ---------------------------------------------------------------------------
# SafetyConfig
# ---------------------------------------------------------------------------

class TestSafetyConfig(unittest.TestCase):
    def test_defaults_are_strict(self):
        cfg = SafetyConfig()
        self.assertTrue(cfg.enabled)
        self.assertTrue(cfg.block_monitor_on_ssh_iface)
        self.assertTrue(cfg.block_monitor_on_management)
        self.assertTrue(cfg.block_kill_management_supplicant)
        self.assertFalse(cfg.armed_override)
        self.assertEqual(cfg.explicit_safe_ifaces, [])

    def test_from_dict_filters_unknown_keys(self):
        cfg = SafetyConfig.from_dict({
            "enabled": False,
            "armed_override": True,
            "totally_unknown_key": "ignored",
        })
        self.assertFalse(cfg.enabled)
        self.assertTrue(cfg.armed_override)
        self.assertFalse(hasattr(cfg, "totally_unknown_key"))

    def test_from_dict_none_returns_defaults(self):
        cfg = SafetyConfig.from_dict(None)
        self.assertTrue(cfg.enabled)


# ---------------------------------------------------------------------------
# SSHGuard — the hard gate
# ---------------------------------------------------------------------------

INTERFACES = {"monitor": "wlan0", "attack": "wlan1", "management": "wlan2"}


class TestSSHGuardBasics(unittest.TestCase):
    def test_management_iface_blocked_by_default(self):
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=None)
        with self.assertRaises(SafetyViolation) as cm:
            guard.assert_safe_to_modify("wlan2")
        self.assertIn("management interface", str(cm.exception))

    def test_non_management_iface_allowed_when_no_ssh(self):
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=None)
        guard.assert_safe_to_modify("wlan0")  # monitor
        guard.assert_safe_to_modify("wlan1")  # attack

    def test_safety_disabled_allows_everything(self):
        cfg = SafetyConfig(enabled=False)
        guard = SSHGuard(cfg, INTERFACES, ssh_session=None)
        guard.assert_safe_to_modify("wlan2")  # management — would normally raise

    def test_armed_override_allows_management(self):
        cfg = SafetyConfig(armed_override=True)
        guard = SSHGuard(cfg, INTERFACES, ssh_session=None)
        guard.assert_safe_to_modify("wlan2")  # bypassed

    def test_explicit_safe_iface_allowed(self):
        cfg = SafetyConfig(explicit_safe_ifaces=["wlan2"])
        guard = SSHGuard(cfg, INTERFACES, ssh_session=None)
        guard.assert_safe_to_modify("wlan2")


class TestSSHGuardWithActiveSSH(unittest.TestCase):
    def setUp(self):
        self.session = {"source": "env", "client_ip": "192.168.1.42", "server_ip": ""}

    @patch("core.safety.get_iface_route_for_ip", return_value="wlan2")
    def test_blocks_modifying_ssh_iface(self, _mock):
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=self.session)
        # wlan2 is both management AND ssh-bearing → both rules trigger,
        # management rule fires first.
        with self.assertRaises(SafetyViolation):
            guard.assert_safe_to_modify("wlan2")

    @patch("core.safety.get_iface_route_for_ip", return_value="wlan0")
    def test_blocks_when_ssh_rides_monitor_iface(self, _mock):
        # SSH happens to ride over the iface we want to put in monitor mode.
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=self.session)
        with self.assertRaises(SafetyViolation) as cm:
            guard.assert_safe_to_modify("wlan0")
        self.assertIn("SSH session", str(cm.exception))

    @patch("core.safety.get_iface_route_for_ip", return_value="eth0")
    def test_allows_when_ssh_on_unrelated_iface(self, _mock):
        # SSH over wired Ethernet — wifi work is fine.
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=self.session)
        guard.assert_safe_to_modify("wlan0")
        guard.assert_safe_to_modify("wlan1")

    @patch("core.safety.get_iface_route_for_ip", return_value=None)
    def test_unknown_ssh_iface_does_not_block_arbitrary_ifaces(self, _mock):
        # If we can't tell which iface SSH rides over, we don't get to block
        # everything — only the management-iface hard rule applies.
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=self.session)
        guard.assert_safe_to_modify("wlan0")
        with self.assertRaises(SafetyViolation):
            guard.assert_safe_to_modify("wlan2")  # management still blocked


class TestSSHGuardSupplicantFiltering(unittest.TestCase):
    def test_filters_out_management_supplicant(self):
        guard = SSHGuard(SafetyConfig(), INTERFACES, ssh_session=None)
        result = guard.assert_safe_to_kill_supplicant({
            "wlan0": [101],   # monitor → safe
            "wlan1": [102],   # attack → safe
            "wlan2": [103],   # management → MUST be filtered out
        })
        self.assertIn(101, result)
        self.assertIn(102, result)
        self.assertNotIn(103, result)

    def test_armed_override_kills_all(self):
        cfg = SafetyConfig(armed_override=True)
        guard = SSHGuard(cfg, INTERFACES, ssh_session=None)
        result = guard.assert_safe_to_kill_supplicant({
            "wlan0": [101], "wlan2": [103],
        })
        self.assertEqual(sorted(result), [101, 103])


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

class TestPreflight(unittest.TestCase):
    def test_clean_config_passes(self):
        config = {"safety": {}}
        result = preflight_check(config, INTERFACES, ssh_session=None)
        self.assertTrue(result.ok)
        self.assertEqual(result.fatal_errors, [])

    def test_duplicate_iface_assignment_is_fatal(self):
        # Same iface assigned to two roles — single_interface_mode footgun
        bad_ifaces = {"monitor": "wlan0", "attack": "wlan0", "management": "wlan0"}
        result = preflight_check({}, bad_ifaces, ssh_session=None)
        self.assertFalse(result.ok)
        self.assertTrue(any("BOTH" in e for e in result.fatal_errors))

    def test_duplicate_iface_with_armed_override_warns_only(self):
        bad_ifaces = {"monitor": "wlan0", "attack": "wlan0", "management": "wlan0"}
        config = {"safety": {"armed_override": True}}
        result = preflight_check(config, bad_ifaces, ssh_session=None)
        self.assertTrue(result.ok)  # operator accepted risk
        self.assertTrue(any("BOTH" in w for w in result.warnings))

    @patch("core.safety.get_iface_route_for_ip", return_value="wlan0")
    @patch("core.safety.iface_has_ip", return_value=True)
    @patch("core.safety.get_iface_mode", return_value="managed")
    def test_ssh_riding_monitor_iface_is_fatal(self, *_mocks):
        sess = {"source": "env", "client_ip": "192.168.1.42", "server_ip": ""}
        result = preflight_check({}, INTERFACES, ssh_session=sess)
        self.assertFalse(result.ok)
        self.assertTrue(any("sever SSH" in e for e in result.fatal_errors))

    @patch("core.safety.get_iface_route_for_ip", return_value="eth0")
    @patch("core.safety.iface_has_ip", return_value=True)
    @patch("core.safety.get_iface_mode", return_value="managed")
    def test_ssh_over_ethernet_is_fine(self, *_mocks):
        sess = {"source": "env", "client_ip": "192.168.1.42", "server_ip": ""}
        result = preflight_check({}, INTERFACES, ssh_session=sess)
        self.assertTrue(result.ok)


class TestFindSupplicantPids(unittest.TestCase):
    """Pure-Python smoke test: function returns a dict on every platform.

    On Windows / non-Linux it returns {}. On Linux the contents depend on
    the host. We don't try to spawn fake processes here — the value is in
    asserting the return shape and that we don't crash.
    """

    def test_returns_dict(self):
        from core.safety import find_supplicant_pids_by_iface
        result = find_supplicant_pids_by_iface()
        self.assertIsInstance(result, dict)
        for k, v in result.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, list)
            for pid in v:
                self.assertIsInstance(pid, int)


if __name__ == "__main__":
    unittest.main()
