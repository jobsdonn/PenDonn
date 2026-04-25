"""Unit tests for core.secure_io — runs anywhere with stdlib only."""

import os
import stat
import sys
import unittest

from core import secure_io
from core.secure_io import (
    cleanup_secure_temp_dir,
    encode_wpa_supplicant_psk,
    encode_wpa_supplicant_ssid,
    sanitize_hostapd_value,
    sanitize_iface_name,
    secure_temp_config,
)


class TestSecureTempConfig(unittest.TestCase):
    def tearDown(self):
        cleanup_secure_temp_dir()

    def test_returns_existing_writable_path(self):
        path = secure_temp_config("hostapd")
        try:
            self.assertTrue(os.path.exists(path))
            with open(path, "w") as f:
                f.write("test")
            with open(path) as f:
                self.assertEqual(f.read(), "test")
        finally:
            os.remove(path)

    def test_file_is_inside_secure_dir(self):
        a = secure_temp_config("a")
        b = secure_temp_config("b")
        self.assertEqual(os.path.dirname(a), os.path.dirname(b))
        os.remove(a)
        os.remove(b)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits N/A on Windows")
    def test_dir_is_0700(self):
        path = secure_temp_config("x")
        try:
            mode = stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode)
            self.assertEqual(mode, 0o700)
        finally:
            os.remove(path)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits N/A on Windows")
    def test_file_is_0600(self):
        path = secure_temp_config("x")
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
        finally:
            os.remove(path)

    def test_cleanup_removes_dir(self):
        path = secure_temp_config("y")
        secure_dir = os.path.dirname(path)
        cleanup_secure_temp_dir()
        self.assertFalse(os.path.exists(secure_dir))


class TestSanitizeIfaceName(unittest.TestCase):
    def test_accepts_typical_iface_names(self):
        for name in ("wlan0", "wlan1", "eth0", "wlp3s0", "mon0", "wlan0.1"):
            self.assertEqual(sanitize_iface_name(name), name)

    def test_rejects_shell_metacharacters(self):
        for bad in ("wlan0; rm -rf /", "wlan0|cat", "wlan 0", "wlan0$VAR", "../etc"):
            with self.assertRaises(ValueError):
                sanitize_iface_name(bad)

    def test_rejects_empty_or_long(self):
        with self.assertRaises(ValueError):
            sanitize_iface_name("")
        with self.assertRaises(ValueError):
            sanitize_iface_name("a" * 16)


class TestSanitizeHostapdValue(unittest.TestCase):
    def test_accepts_normal_ssids(self):
        for s in ("LinusTest", "Kjell-Guest", "wifi 5G", "Café", "✓"):
            self.assertEqual(sanitize_hostapd_value(s, field="ssid"), s)

    def test_rejects_newline_injection(self):
        # The classic injection: SSID ends with a newline plus another directive.
        evil = "MyNet\nbssid=DE:AD:BE:EF:00:00"
        with self.assertRaises(ValueError) as cm:
            sanitize_hostapd_value(evil, field="ssid")
        self.assertIn("newline", str(cm.exception))

    def test_rejects_carriage_return(self):
        with self.assertRaises(ValueError):
            sanitize_hostapd_value("evil\rinject", field="ssid")

    def test_rejects_null_byte(self):
        with self.assertRaises(ValueError):
            sanitize_hostapd_value("foo\x00bar", field="ssid")

    def test_rejects_too_long(self):
        with self.assertRaises(ValueError):
            sanitize_hostapd_value("a" * 33, field="ssid")  # >32 bytes

    def test_unicode_byte_length_enforced(self):
        # 11 emoji = 44 UTF-8 bytes, over the 32 limit
        with self.assertRaises(ValueError):
            sanitize_hostapd_value("✓" * 11, field="ssid")

    def test_empty_rejected_unless_allowed(self):
        with self.assertRaises(ValueError):
            sanitize_hostapd_value("", field="ssid")
        # explicit allow_empty for hidden-SSID hostapd 'ignore_broadcast_ssid' line
        self.assertEqual(sanitize_hostapd_value("", allow_empty=True), "")


class TestEncodeWpaSupplicantSsid(unittest.TestCase):
    def test_round_trip_simple(self):
        # "test" → 74657374
        self.assertEqual(encode_wpa_supplicant_ssid("test"), "74657374")

    def test_handles_unicode(self):
        # ASCII-safe representation regardless of input chars
        out = encode_wpa_supplicant_ssid("Café")
        bytes.fromhex(out)  # parses
        self.assertTrue(all(c in "0123456789abcdef" for c in out))

    def test_rejects_oversize(self):
        with self.assertRaises(ValueError):
            encode_wpa_supplicant_ssid("a" * 33)

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            encode_wpa_supplicant_ssid("")


class TestEncodeWpaSupplicantPsk(unittest.TestCase):
    def test_quotes_and_escapes_normal_passphrase(self):
        self.assertEqual(encode_wpa_supplicant_psk("simplepass"), '"simplepass"')

    def test_escapes_quotes_and_backslashes(self):
        self.assertEqual(
            encode_wpa_supplicant_psk('weird"pass\\back'),
            '"weird\\"pass\\\\back"',
        )

    def test_passes_through_64_hex_psk_unquoted(self):
        raw = "a" * 64
        self.assertEqual(encode_wpa_supplicant_psk(raw), raw)

    def test_rejects_too_short(self):
        with self.assertRaises(ValueError):
            encode_wpa_supplicant_psk("short")

    def test_rejects_too_long_ascii(self):
        # 64-char that ISN'T pure hex falls into the ASCII branch; max is 63
        with self.assertRaises(ValueError):
            encode_wpa_supplicant_psk("g" * 64)

    def test_rejects_newline_injection_in_psk(self):
        with self.assertRaises(ValueError):
            encode_wpa_supplicant_psk("good_pass\nkey_mgmt=NONE")


if __name__ == "__main__":
    unittest.main()
