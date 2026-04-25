"""Tests for core.config_loader — runs anywhere with stdlib only."""

import json
import os
import stat
import sys
import tempfile
import unittest

from core.config_loader import (
    PLACEHOLDER_SECRETS,
    ensure_persistent_secret,
    load_config,
    local_overlay_path,
)


def write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_base_when_no_overlay(self):
        write_json(self.path, {"web": {"port": 8080}})
        cfg = load_config(self.path)
        # The targeting normalizer always populates allowlist + mirrors to
        # whitelist for back-compat, so a base-only load now also exposes
        # those defaulted keys.
        self.assertEqual(cfg["web"], {"port": 8080})
        self.assertEqual(cfg["allowlist"], {"ssids": [], "strict": True})
        self.assertEqual(cfg["whitelist"], {"ssids": []})

    def test_overlay_replaces_scalar(self):
        write_json(self.path, {"web": {"port": 8080, "host": "127.0.0.1"}})
        write_json(local_overlay_path(self.path), {"web": {"port": 9090}})
        cfg = load_config(self.path)
        self.assertEqual(cfg["web"]["port"], 9090)
        self.assertEqual(cfg["web"]["host"], "127.0.0.1")  # untouched

    def test_overlay_deep_merges_dicts(self):
        write_json(self.path, {
            "wifi": {"monitor_interface": "wlan0", "channel_hop_interval": 2},
            "safety": {"enabled": True},
        })
        write_json(local_overlay_path(self.path), {
            "wifi": {"monitor_mac": "aa:bb:cc:dd:ee:ff"},
        })
        cfg = load_config(self.path)
        self.assertEqual(cfg["wifi"]["monitor_interface"], "wlan0")
        self.assertEqual(cfg["wifi"]["channel_hop_interval"], 2)
        self.assertEqual(cfg["wifi"]["monitor_mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(cfg["safety"], {"enabled": True})

    def test_overlay_replaces_lists_wholesale(self):
        # Lists are NOT deep-merged — overlay replaces the whole list. This
        # is the right behavior for things like `whitelist.ssids`.
        write_json(self.path, {"whitelist": {"ssids": ["A", "B"]}})
        write_json(local_overlay_path(self.path), {"whitelist": {"ssids": ["C"]}})
        cfg = load_config(self.path)
        self.assertEqual(cfg["whitelist"]["ssids"], ["C"])

    def test_documentation_keys_stripped(self):
        write_json(self.path, {
            "_README": "ignored",
            "wifi": {"_comment": "ignored too", "monitor_interface": "wlan0"},
        })
        cfg = load_config(self.path)
        self.assertNotIn("_README", cfg)
        self.assertNotIn("_comment", cfg["wifi"])
        self.assertEqual(cfg["wifi"]["monitor_interface"], "wlan0")

    def test_corrupt_overlay_falls_back_to_base(self):
        write_json(self.path, {"web": {"port": 8080}})
        # Write invalid JSON to overlay
        with open(local_overlay_path(self.path), "w") as f:
            f.write("{not valid json")
        cfg = load_config(self.path)
        self.assertEqual(cfg["web"], {"port": 8080})
        # Normalizer still runs even when overlay is bad
        self.assertEqual(cfg["allowlist"], {"ssids": [], "strict": True})


class TestEnsurePersistentSecret(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")
        write_json(self.path, {})

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_existing_secret_unchanged(self):
        cfg = {"web": {"secret_key": "a" * 64}}
        result = ensure_persistent_secret(cfg, self.path)
        self.assertEqual(result, "a" * 64)
        # No .local file should be created
        self.assertFalse(os.path.exists(local_overlay_path(self.path)))

    def test_generates_secret_for_empty(self):
        cfg = {"web": {"secret_key": ""}}
        result = ensure_persistent_secret(cfg, self.path)
        self.assertNotIn(result, PLACEHOLDER_SECRETS)
        self.assertEqual(len(result), 64)  # token_hex(32) -> 64 hex chars
        # Mutated in place
        self.assertEqual(cfg["web"]["secret_key"], result)
        # Written to .local
        with open(local_overlay_path(self.path)) as f:
            persisted = json.load(f)
        self.assertEqual(persisted["web"]["secret_key"], result)

    def test_generates_secret_for_placeholder(self):
        cfg = {"web": {"secret_key": "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"}}
        result = ensure_persistent_secret(cfg, self.path)
        self.assertNotIn(result, PLACEHOLDER_SECRETS)
        self.assertEqual(len(result), 64)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits N/A on Windows")
    def test_local_file_is_0600(self):
        cfg = {"web": {"secret_key": ""}}
        ensure_persistent_secret(cfg, self.path)
        mode = stat.S_IMODE(os.stat(local_overlay_path(self.path)).st_mode)
        self.assertEqual(mode, 0o600)

    def test_does_not_clobber_existing_local_overlay(self):
        # Operator already wrote a basic_auth password hash to .local;
        # generating a secret must preserve it.
        write_json(local_overlay_path(self.path), {
            "web": {"basic_auth": {"username": "linus", "password_hash": "x"}},
        })
        cfg = {"web": {"secret_key": ""}}
        ensure_persistent_secret(cfg, self.path)
        with open(local_overlay_path(self.path)) as f:
            persisted = json.load(f)
        self.assertEqual(persisted["web"]["basic_auth"]["username"], "linus")
        self.assertIn("secret_key", persisted["web"])

    def test_idempotent_after_first_run(self):
        cfg1 = {"web": {"secret_key": ""}}
        first = ensure_persistent_secret(cfg1, self.path)
        # Simulate a process restart — base config has empty secret, but
        # .local overlay now has the persisted one. Caller would normally
        # call load_config first to merge them.
        cfg2 = load_config(self.path)
        # In real usage, base config has empty secret_key field; here our
        # test base is just `{}` so .local provides everything.
        second = ensure_persistent_secret(cfg2, self.path)
        self.assertEqual(first, second)


class TestTargetingNormalization(unittest.TestCase):
    """Phase 2A: whitelist <-> allowlist normalization + strict-default."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_whitelist_is_promoted_to_allowlist(self):
        write_json(self.path, {"whitelist": {"ssids": ["LegacyHome"]}})
        cfg = load_config(self.path)
        self.assertEqual(cfg["allowlist"]["ssids"], ["LegacyHome"])
        self.assertTrue(cfg["allowlist"]["strict"])
        # Mirror still present for legacy reader
        self.assertEqual(cfg["whitelist"]["ssids"], ["LegacyHome"])

    def test_modern_allowlist_takes_precedence_when_both_present(self):
        # Base has legacy `whitelist`; overlay has modern `allowlist`.
        write_json(self.path, {"whitelist": {"ssids": ["OldA", "OldB"]}})
        write_json(local_overlay_path(self.path), {
            "allowlist": {"ssids": ["NewC"], "strict": False},
        })
        cfg = load_config(self.path)
        # allowlist wins; whitelist mirrors allowlist's ssids (not the base's)
        self.assertEqual(cfg["allowlist"]["ssids"], ["NewC"])
        self.assertFalse(cfg["allowlist"]["strict"])
        self.assertEqual(cfg["whitelist"]["ssids"], ["NewC"])

    def test_default_strict_true_when_only_ssids_given(self):
        write_json(self.path, {"allowlist": {"ssids": ["Foo"]}})
        cfg = load_config(self.path)
        self.assertTrue(cfg["allowlist"]["strict"])

    def test_explicit_strict_false_is_preserved(self):
        write_json(self.path, {"allowlist": {"ssids": [], "strict": False}})
        cfg = load_config(self.path)
        self.assertFalse(cfg["allowlist"]["strict"])

    def test_no_targeting_section_at_all_yields_safe_defaults(self):
        write_json(self.path, {"web": {"port": 8080}})
        cfg = load_config(self.path)
        self.assertEqual(cfg["allowlist"], {"ssids": [], "strict": True})


if __name__ == "__main__":
    unittest.main()
