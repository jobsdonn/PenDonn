"""Unit tests for the hcxdumptool capture path in core.wifi_scanner.

The capture engine migrated from airodump+aireplay+hcxdumptool-side-probe
to a single hcxdumptool process (commit migrating off airodump). The
safety contract that used to live in `_trigger_pmkid` — "must use a BPF
filter scoping to the target BSSID, otherwise we attack neighbours" —
now lives in `_start_handshake_capture`. These tests verify that.

Also: the channel-format helper `_channel_to_hcx` (band suffixes for
hcxdumptool 6.3+).
"""

import unittest
from unittest.mock import MagicMock, patch

from core import wifi_scanner as ws


def _make_scanner(active_captures=None, attack_iface_in_monitor=False):
    """Build a WiFiScanner-shaped object with just the attrs the
    capture path uses. Avoids the constructor (which calls into
    interface_manager / subprocess on Linux ifaces that don't exist
    on dev hosts)."""
    s = MagicMock(spec=[])
    s.interface = "wlan0"
    s.attack_interface = "wlan1"
    s.management_interface = "wlan2"
    s.active_captures = active_captures if active_captures is not None else {}
    s.handshake_dir = "/tmp/handshakes_test"
    s.enumeration_active = False
    import threading
    s.enumeration_lock = threading.Lock()
    s._attack_iface_in_monitor = attack_iface_in_monitor

    # Bind the real methods.
    s._start_handshake_capture = ws.WiFiScanner._start_handshake_capture.__get__(s, type(s))
    s._channel_to_hcx = ws.WiFiScanner._channel_to_hcx
    s._trigger_pmkid = ws.WiFiScanner._trigger_pmkid.__get__(s, type(s))
    s._send_deauth_delayed = ws.WiFiScanner._send_deauth_delayed.__get__(s, type(s))
    return s


class TestChannelToHcx(unittest.TestCase):
    """hcxdumptool 6.3+ requires band suffix on -c (4a, 36b)."""

    def test_2_4ghz_gets_a_suffix(self):
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(1), '1a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(4), '4a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(11), '11a')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(13), '13a')

    def test_5ghz_gets_b_suffix(self):
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(36), '36b')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(149), '149b')
        self.assertEqual(ws.WiFiScanner._channel_to_hcx(165), '165b')


class TestCaptureBpfScoping(unittest.TestCase):
    """SAFETY-CRITICAL: hcxdumptool must always be scoped to a single
    BSSID via BPF. Without it, hcxdumptool actively probes every AP on
    the channel — replays the 2026-04-25 first-boot incident."""

    def test_capture_command_includes_bpf_for_target_bssid(self):
        bssid = "B0:19:21:ED:84:FA"
        ssid = "Kjell-BYOD"
        channel = 4

        scanner = _make_scanner()

        captured_run = []   # subprocess.run calls (BPF compile)
        captured_popen = []  # subprocess.Popen calls (hcxdumptool capture)

        def fake_run(cmd, **kwargs):
            captured_run.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "1,2,3,4\n"  # plausible bpfc output
            r.stderr = ""
            return r

        def fake_popen(cmd, **kwargs):
            captured_popen.append(cmd)
            p = MagicMock()
            p.poll.return_value = None  # alive — survives the 1s startup check
            p.returncode = None
            return p

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.run.side_effect = fake_run
            mock_sp.Popen.side_effect = fake_popen
            mock_sp.DEVNULL = -3
            mock_sp.PIPE = -1
            mock_sp.TimeoutExpired = TimeoutError
            scanner._start_handshake_capture(bssid, ssid, channel)

        # --bpfc was compiled for the target BSSID
        self.assertEqual(len(captured_run), 1, "expected one --bpfc compile call")
        bpfc_cmd = captured_run[0]
        self.assertEqual(bpfc_cmd[0], 'hcxdumptool')
        bpfc_arg = next(a for a in bpfc_cmd if a.startswith('--bpfc='))
        self.assertIn('b01921ed84fa', bpfc_arg.lower(),
                      "BPF expression must reference target BSSID")
        # Filter scopes by MAC in any address field (`wlan host`).
        # If you tighten this to `wlan addr3`, the rtl8821au driver under-
        # matches and capture stalls — verified live 2026-04-26.
        self.assertIn('host', bpfc_arg)

        # hcxdumptool capture invoked with --bpf=<file>
        self.assertEqual(len(captured_popen), 1, "expected one hcxdumptool capture")
        cmd = captured_popen[0]
        self.assertEqual(cmd[0], 'hcxdumptool')
        self.assertIn('-i', cmd)
        self.assertEqual(cmd[cmd.index('-i') + 1], 'wlan0',
                         "capture must use the monitor (capture) iface")
        self.assertIn('-c', cmd)
        self.assertEqual(cmd[cmd.index('-c') + 1], '4a',
                         "channel must include band suffix")

        bpf_args = [a for a in cmd if a.startswith('--bpf=')]
        self.assertEqual(len(bpf_args), 1,
                         "BPF filter missing — hcxdumptool would probe every AP")

        # Should exit early on any EAPOL/PMKID hit
        self.assertIn('--exitoneapol=7', cmd)

        # Capture is added to active_captures
        self.assertIn(bssid, scanner.active_captures)
        self.assertTrue(scanner.active_captures[bssid]['capture_file'].endswith('.pcapng'))

    def test_capture_skipped_when_enumeration_active(self):
        """While enumerator is active, capture must not start."""
        scanner = _make_scanner()
        scanner.enumeration_active = True

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.TimeoutExpired = TimeoutError
            scanner._start_handshake_capture("AA:BB:CC:DD:EE:FF", "X", 6)
            mock_sp.Popen.assert_not_called()
            mock_sp.run.assert_not_called()

    def test_capture_skipped_when_already_capturing(self):
        """Only one capture at a time on the shared monitor iface."""
        scanner = _make_scanner(active_captures={"OTHER:BSSID": {"ssid": "X"}})

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.TimeoutExpired = TimeoutError
            scanner._start_handshake_capture("AA:BB:CC:DD:EE:FF", "X", 6)
            mock_sp.Popen.assert_not_called()

    def test_capture_handles_missing_hcxdumptool(self):
        """If hcxdumptool isn't installed, log error and bail cleanly."""
        scanner = _make_scanner()

        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.run.side_effect = FileNotFoundError()
            mock_sp.TimeoutExpired = TimeoutError
            scanner._start_handshake_capture("AA:BB:CC:DD:EE:FF", "X", 6)
            # Should not have populated active_captures
            self.assertEqual(scanner.active_captures, {})


class TestDeprecatedMethodsAreNoOp(unittest.TestCase):
    """The old _trigger_pmkid and _send_deauth_delayed are now no-ops
    (hcxdumptool handles both internally). Verify they don't crash and
    don't try to spawn subprocesses."""

    def test_trigger_pmkid_is_noop(self):
        scanner = _make_scanner()
        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.TimeoutExpired = TimeoutError
            result = scanner._trigger_pmkid("AA:BB:CC:DD:EE:FF", "X", 6)
            self.assertIsNone(result)
            mock_sp.Popen.assert_not_called()
            mock_sp.run.assert_not_called()

    def test_send_deauth_delayed_is_noop(self):
        scanner = _make_scanner()
        with patch.object(ws, 'subprocess') as mock_sp, \
             patch.object(ws.time, 'sleep'):
            mock_sp.TimeoutExpired = TimeoutError
            result = scanner._send_deauth_delayed("AA:BB:CC:DD:EE:FF", 6)
            self.assertIsNone(result)
            mock_sp.Popen.assert_not_called()
            mock_sp.run.assert_not_called()


class TestParseEncryption(unittest.TestCase):
    """_parse_encryption correctly classifies WPA3, WPA2, WPA, WEP, Open."""

    def _parse(self, privacy: str, auth: str = "", cipher: str = "") -> str:
        s = _make_scanner()
        s._parse_encryption = ws.WiFiScanner._parse_encryption.__get__(s, type(s))
        row = {'Authentication': auth, 'Cipher': cipher}
        return s._parse_encryption(privacy, row)

    def test_wpa3_sae_auth(self):
        self.assertEqual(self._parse("WPA3", "SAE"), "WPA3")

    def test_wpa3_privacy_only(self):
        self.assertEqual(self._parse("WPA3", ""), "WPA3")

    def test_wpa3_transition_both_in_privacy(self):
        result = self._parse("WPA2 WPA3", "PSK SAE")
        self.assertIn("transition", result.lower())

    def test_wpa3_transition_psk_sae_auth(self):
        result = self._parse("WPA2", "PSK SAE")
        self.assertIn("transition", result.lower())

    def test_wpa2(self):
        self.assertEqual(self._parse("WPA2", "PSK"), "WPA2")

    def test_wpa(self):
        self.assertEqual(self._parse("WPA", "PSK"), "WPA")

    def test_open(self):
        self.assertEqual(self._parse("OPN", ""), "Open")

    def test_wep(self):
        self.assertEqual(self._parse("WEP", ""), "WEP")


if __name__ == '__main__':
    unittest.main()
