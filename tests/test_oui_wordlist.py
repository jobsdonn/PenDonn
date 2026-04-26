"""Unit tests for core.oui_wordlist — OUI-based PSK pre-guess."""

import os
import unittest
from core.oui_wordlist import (
    _lookup_vendor,
    _ssid_patterns,
    _bssid_patterns,
    _vendor_patterns,
    generate_oui_wordlist,
)


class TestOuiLookup(unittest.TestCase):
    def test_tplink_oui_recognised(self):
        # D8:0D:17 is a known TP-Link OUI
        self.assertEqual(_lookup_vendor("D8:0D:17:AA:BB:CC"), "tplink")

    def test_asus_oui_recognised(self):
        self.assertEqual(_lookup_vendor("10:7B:44:11:22:33"), "asus")

    def test_fritzbox_oui_recognised(self):
        self.assertEqual(_lookup_vendor("3C:37:86:AA:BB:CC"), "fritzbox")

    def test_unknown_oui_returns_none(self):
        self.assertIsNone(_lookup_vendor("00:00:00:11:22:33"))

    def test_short_bssid_returns_none(self):
        self.assertIsNone(_lookup_vendor("FF:FF"))


class TestSsidPatterns(unittest.TestCase):
    def test_ssid_itself_included(self):
        self.assertIn("MyWifi123", _ssid_patterns("MyWifi123"))

    def test_short_ssid_excluded(self):
        # "Wi" is 2 chars — patterns from it would be <8 chars → filtered
        patterns = _ssid_patterns("Wi")
        # Any pattern under 8 chars should be absent
        for p in patterns:
            self.assertGreaterEqual(len(p), 8)

    def test_suffix_variants_generated(self):
        patterns = _ssid_patterns("MyRouter")
        self.assertIn("MyRouter1234", patterns)
        self.assertIn("MyRouter!", patterns)

    def test_empty_ssid_safe(self):
        self.assertEqual(_ssid_patterns(""), [])


class TestBssidPatterns(unittest.TestCase):
    def test_last8_upper_included(self):
        patterns = _bssid_patterns("D8:0D:17:AA:BB:CC")
        self.assertIn("17AABBCC", patterns)

    def test_last8_lower_included(self):
        patterns = _bssid_patterns("D8:0D:17:AA:BB:CC")
        self.assertIn("17aabbcc", patterns)

    def test_tplink_prefix_pattern(self):
        patterns = _bssid_patterns("D8:0D:17:AA:BB:CC")
        self.assertTrue(any("tp-link" in p.lower() for p in patterns))

    def test_short_bssid_safe(self):
        # Should not crash, just return an empty list or short candidates
        patterns = _bssid_patterns("AA:BB")
        self.assertIsInstance(patterns, list)


class TestVendorPatterns(unittest.TestCase):
    def test_tplink_includes_last8(self):
        p = _vendor_patterns("tplink", "D8:0D:17:AA:BB:CC", "TP-Link_Test")
        self.assertTrue(any("17AABBCC" in x or "17aabbcc" in x for x in p))

    def test_all_patterns_within_wpa_len(self):
        for vendor in ("tplink", "asus", "netgear", "dlink", "fritzbox", "zte",
                       "huawei", "tenda", "bt"):
            for p in _vendor_patterns(vendor, "D8:0D:17:AA:BB:CC", "TestNet"):
                self.assertGreaterEqual(len(p), 8, f"{vendor}: {p!r} too short")
                self.assertLessEqual(len(p), 63, f"{vendor}: {p!r} too long")


class TestGenerateOuiWordlist(unittest.TestCase):
    def test_returns_path_for_known_ap(self):
        path = generate_oui_wordlist("D8:0D:17:AA:BB:CC", "TP-Link_AABBCC")
        try:
            self.assertIsNotNone(path)
            self.assertTrue(os.path.isfile(path))
            content = open(path).read()
            # Must contain at least the universal weaks
            self.assertIn("12345678", content)
            # Must contain vendor-derived candidates
            lines = [l for l in content.splitlines() if l]
            self.assertGreater(len(lines), 5)
            # All lines must be valid WPA length
            for l in lines:
                self.assertGreaterEqual(len(l), 8)
                self.assertLessEqual(len(l), 63)
        finally:
            if path and os.path.isfile(path):
                os.unlink(path)

    def test_returns_path_for_unknown_ap(self):
        path = generate_oui_wordlist("00:00:00:AA:BB:CC", "MyNetwork123")
        try:
            self.assertIsNotNone(path)
            content = open(path).read()
            lines = [l for l in content.splitlines() if l]
            self.assertGreater(len(lines), 0)
        finally:
            if path and os.path.isfile(path):
                os.unlink(path)

    def test_no_duplicate_lines(self):
        path = generate_oui_wordlist("D8:0D:17:AA:BB:CC", "TP-Link_AABBCC")
        try:
            lines = open(path).read().splitlines()
            self.assertEqual(len(lines), len(set(lines)), "duplicates found")
        finally:
            if path and os.path.isfile(path):
                os.unlink(path)

    def test_empty_bssid_returns_something(self):
        path = generate_oui_wordlist("", "SomeNetwork12")
        try:
            self.assertIsNotNone(path)
        finally:
            if path and os.path.isfile(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
