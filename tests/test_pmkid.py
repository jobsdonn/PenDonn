"""Unit tests for the PMKID-trigger path in core.wifi_scanner.

Focus: the hcxdumptool invocation must (a) target ONLY the requested BSSID
via filterlist_ap + filtermode=2, (b) lock to the requested channel, and
(c) clean up its temp files. The first guarantee is the safety-critical
one — without filtermode=2, hcxdumptool would actively probe every AP
on the channel (this would replay the 2026-04-25 first-boot incident).
"""

import os
import unittest
from unittest.mock import MagicMock, patch

# Import the module then call _trigger_pmkid against a hand-built instance,
# so we don't have to satisfy the WiFiScanner constructor (which calls
# resolve_interfaces → subprocess on Linux ifaces that don't exist on dev).
from core import wifi_scanner as ws


def _make_scanner(active_captures):
    """Build a WiFiScanner-shaped object with just the attrs _trigger_pmkid uses."""
    s = MagicMock(spec=[])
    s.interface = "wlan0"
    s.attack_interface = "wlan1"
    s.active_captures = active_captures
    # SSHGuard mock — assert_safe_to_modify is a no-op (raises only on real violations)
    s._ssh_guard = MagicMock()
    s._ssh_guard.assert_safe_to_modify = MagicMock(return_value=None)
    # _enable_monitor_mode mock — succeeds silently
    s._enable_monitor_mode = MagicMock(return_value=None)
    # Bind the real methods to our mock so we exercise the actual code.
    s._trigger_pmkid = ws.WiFiScanner._trigger_pmkid.__get__(s, type(s))
    # _channel_to_hcx is a staticmethod — reachable via self._channel_to_hcx(...)
    s._channel_to_hcx = ws.WiFiScanner._channel_to_hcx
    return s


class TestPmkidCommand(unittest.TestCase):
    def test_command_locks_to_target_bssid_and_channel(self):
        """Most important assertion: BPF filter scopes hcxdumptool to one BSSID.

        Without --bpf, hcxdumptool would actively probe every AP it sees
        on the channel — replaying the 2026-04-25 first-boot incident.
        """
        bssid = "B0:19:21:ED:84:FA"
        ssid = "Kjell-BYOD"
        channel = 4

        scanner = _make_scanner({bssid: {"ssid": ssid}})

        captured_cmds = []
        captured_bpfc_args = []

        def fake_popen(cmd, **kwargs):
            captured_cmds.append(cmd)
            proc = MagicMock()
            proc.poll.return_value = 0
            proc.wait.return_value = 0
            proc.returncode = 0
            proc.stderr = None
            return proc

        def fake_run(cmd, **kwargs):
            captured_bpfc_args.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "1,2,3,4,5\n"  # plausible bpfc output
            r.stderr = ""
            return r

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.Popen.side_effect = fake_popen
            mock_sp.run.side_effect = fake_run
            mock_sp.TimeoutExpired = TimeoutError
            scanner._trigger_pmkid(bssid, ssid, channel)

        # First subprocess call: hcxdumptool --bpfc to compile filter
        self.assertEqual(len(captured_bpfc_args), 1)
        bpfc_cmd = captured_bpfc_args[0]
        self.assertEqual(bpfc_cmd[0], 'hcxdumptool')
        self.assertTrue(any(a.startswith('--bpfc=') for a in bpfc_cmd),
                        f"BPF compile invocation missing: {bpfc_cmd}")
        # The BPF expression must reference the target BSSID
        bpfc_arg = next(a for a in bpfc_cmd if a.startswith('--bpfc='))
        self.assertIn('b01921ed84fa', bpfc_arg.lower())
        self.assertIn('addr3', bpfc_arg)

        # Second subprocess call: hcxdumptool itself
        self.assertEqual(len(captured_cmds), 1, "expected one hcxdumptool capture invocation")
        cmd = captured_cmds[0]

        self.assertEqual(cmd[0], 'hcxdumptool')
        self.assertIn('-i', cmd)
        # Must use the attack iface (wlan1), not the monitor (wlan0).
        # wlan0 is busy with airodump; sharing a monitor iface for active
        # tx fails with "driver is busy" on the rtl driver.
        self.assertEqual(cmd[cmd.index('-i') + 1], 'wlan1')
        self.assertIn('-c', cmd)
        # Channel 4 must be formatted with band suffix "a" for 2.4GHz
        self.assertEqual(cmd[cmd.index('-c') + 1], '4a',
                         "hcxdumptool 6.3 requires band suffix on -c (4a for CH 4 / 2.4GHz)")

        # SAFETY-CRITICAL: --bpf=<file> must be present to scope the attack.
        bpf_args = [a for a in cmd if a.startswith('--bpf=')]
        self.assertEqual(len(bpf_args), 1,
                         "BPF filter missing — hcxdumptool would probe every AP")

        # Deauth must be disabled (aireplay handles that on the same iface).
        self.assertIn('--disable_deauthentication', cmd)
        # Exit on PMKID — saves time once we have what we need.
        self.assertIn('--exitoneapol=1', cmd)

    def test_channel_to_hcx_band_suffixes(self):
        """2.4GHz → a, 5GHz → b. (6GHz channel numbers overlap with 5GHz.)"""
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(1), '1a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(4), '4a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(11), '11a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(36), '36b')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(149), '149b')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(165), '165b')

    def test_skips_if_capture_no_longer_active(self):
        """If main capture finalized during the 15s wait, skip the probe entirely."""
        scanner = _make_scanner({})  # empty — capture already gone

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            scanner._trigger_pmkid("AA:BB:CC:DD:EE:FF", "Test", 6)
            mock_sp.Popen.assert_not_called()

    def test_handles_missing_hcxdumptool_gracefully(self):
        """If the binary isn't installed we log + return cleanly, no crash."""
        bssid = "AA:BB:CC:DD:EE:FF"
        scanner = _make_scanner({bssid: {"ssid": "Test"}})

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            # bpfc compile fails first because hcxdumptool isn't installed
            mock_sp.run.side_effect = FileNotFoundError()
            mock_sp.Popen.side_effect = FileNotFoundError()
            mock_sp.TimeoutExpired = TimeoutError
            # Should not raise
            scanner._trigger_pmkid(bssid, "Test", 6)

    def test_cleans_up_temp_files(self):
        """Both BPF file and pcap paths must be considered for cleanup."""
        bssid = "AA:BB:CC:DD:EE:FF"
        scanner = _make_scanner({bssid: {"ssid": "Test"}})

        removed = []

        def fake_popen(cmd, **kwargs):
            proc = MagicMock()
            proc.poll.return_value = 0
            proc.wait.return_value = 0
            proc.returncode = 0
            proc.stderr = None
            return proc

        def fake_run(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 0
            r.stdout = "1,2,3\n"
            r.stderr = ""
            return r

        # Pretend both files exist so the cleanup branch fires for each.
        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'), \
             patch.object(ws.os.path, 'exists', return_value=True), \
             patch.object(ws.os, 'remove', side_effect=lambda p: removed.append(p)):
            mock_sp.Popen.side_effect = fake_popen
            mock_sp.run.side_effect = fake_run
            mock_sp.TimeoutExpired = TimeoutError
            scanner._trigger_pmkid(bssid, "Test", 6)

        self.assertTrue(any('pmkid_filter' in p for p in removed),
                        f"BPF file not cleaned up: {removed}")
        self.assertTrue(any(p.endswith('.pcapng') for p in removed),
                        f"pcap not cleaned up: {removed}")


if __name__ == '__main__':
    unittest.main()
