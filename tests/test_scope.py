"""Tests for scope authorization (core.database + the wifi_scanner gate)."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from core.database import Database


class TestScopeAuthorizationDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, 'pendonn.db')
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close_all() if hasattr(self.db, 'close_all') else None
        self.tmp.cleanup()

    def test_no_authorization_means_unconfirmed(self):
        confirmed, missing = self.db.is_scope_confirmed_for(['Customer-AP-1'])
        self.assertFalse(confirmed)
        self.assertEqual(missing, ['Customer-AP-1'])

    def test_empty_allowlist_is_trivially_confirmed(self):
        confirmed, missing = self.db.is_scope_confirmed_for([])
        self.assertTrue(confirmed)
        self.assertEqual(missing, [])

    def test_confirm_then_check(self):
        self.db.confirm_scope(['AP-1', 'AP-2'], confirmed_by='linus', note='engagement #42')
        confirmed, missing = self.db.is_scope_confirmed_for(['AP-1', 'AP-2'])
        self.assertTrue(confirmed)
        self.assertEqual(missing, [])

    def test_confirm_does_not_cover_new_ssid(self):
        self.db.confirm_scope(['AP-1'], confirmed_by='linus')
        confirmed, missing = self.db.is_scope_confirmed_for(['AP-1', 'AP-2'])
        self.assertFalse(confirmed)
        self.assertEqual(missing, ['AP-2'])

    def test_shrinking_allowlist_stays_confirmed(self):
        """If we authorize [A, B] and then drop B, [A] is still covered."""
        self.db.confirm_scope(['AP-1', 'AP-2'], confirmed_by='linus')
        confirmed, missing = self.db.is_scope_confirmed_for(['AP-1'])
        self.assertTrue(confirmed)
        self.assertEqual(missing, [])

    def test_revoke_removes_authorization(self):
        self.db.confirm_scope(['AP-1'], confirmed_by='linus')
        self.assertTrue(self.db.is_scope_confirmed_for(['AP-1'])[0])
        revoked = self.db.revoke_scope(revoked_by='linus')
        self.assertTrue(revoked)
        self.assertFalse(self.db.is_scope_confirmed_for(['AP-1'])[0])

    def test_revoke_with_no_active_authorization_is_noop(self):
        self.assertFalse(self.db.revoke_scope(revoked_by='linus'))

    def test_re_confirm_after_revoke(self):
        self.db.confirm_scope(['AP-1'], confirmed_by='linus')
        self.db.revoke_scope(revoked_by='linus')
        self.db.confirm_scope(['AP-1', 'AP-2'], confirmed_by='linus')
        confirmed, missing = self.db.is_scope_confirmed_for(['AP-1', 'AP-2'])
        self.assertTrue(confirmed)
        self.assertEqual(missing, [])

    def test_get_active_scope_returns_latest_non_revoked(self):
        self.db.confirm_scope(['AP-1'], confirmed_by='alice', note='first')
        self.db.confirm_scope(['AP-1', 'AP-2'], confirmed_by='bob', note='second')
        active = self.db.get_active_scope()
        self.assertIsNotNone(active)
        self.assertEqual(active['confirmed_by'], 'bob')
        self.assertEqual(set(active['ssids']), {'AP-1', 'AP-2'})
        self.assertEqual(active['note'], 'second')

    def test_active_scope_none_when_all_revoked(self):
        self.db.confirm_scope(['AP-1'], confirmed_by='linus')
        self.db.revoke_scope(revoked_by='linus')
        self.assertIsNone(self.db.get_active_scope())


class TestWiFiScannerScopeGate(unittest.TestCase):
    """The _scope_allows() gate sits between targeting and capture. Mock the
    db so we test only the gate behaviour, not the full scanner pipeline."""

    def _scanner_with(self, allowlist_ssids, active_scope):
        """Construct a minimal stand-in for the WiFiScanner gate.

        Importing WiFiScanner pulls in subprocess/airodump deps that aren't
        worth dragging into a unit test. We replicate the _scope_allows
        logic directly against a mocked db.
        """
        from core.wifi_scanner import WiFiScanner

        scanner = WiFiScanner.__new__(WiFiScanner)
        scanner.allowlist_ssids = set(allowlist_ssids)
        scanner.db = MagicMock()
        scanner.db.get_active_scope.return_value = active_scope
        return scanner

    def test_empty_allowlist_short_circuits_to_true(self):
        from core.wifi_scanner import WiFiScanner
        s = self._scanner_with(allowlist_ssids=[], active_scope=None)
        self.assertTrue(WiFiScanner._scope_allows(s, 'any-ssid'))

    def test_no_active_scope_denies(self):
        from core.wifi_scanner import WiFiScanner
        s = self._scanner_with(allowlist_ssids=['AP-1'], active_scope=None)
        self.assertFalse(WiFiScanner._scope_allows(s, 'AP-1'))

    def test_active_scope_with_matching_ssid_allows(self):
        from core.wifi_scanner import WiFiScanner
        s = self._scanner_with(
            allowlist_ssids=['AP-1'],
            active_scope={'ssids': ['AP-1']},
        )
        self.assertTrue(WiFiScanner._scope_allows(s, 'AP-1'))

    def test_active_scope_missing_ssid_denies(self):
        from core.wifi_scanner import WiFiScanner
        s = self._scanner_with(
            allowlist_ssids=['AP-1', 'AP-2'],
            active_scope={'ssids': ['AP-1']},
        )
        self.assertFalse(WiFiScanner._scope_allows(s, 'AP-2'))

    def test_db_failure_denies(self):
        """If the DB is unreachable, fail closed — don't open the gate."""
        from core.wifi_scanner import WiFiScanner
        s = self._scanner_with(allowlist_ssids=['AP-1'], active_scope=None)
        s.db.get_active_scope.side_effect = Exception('db down')
        self.assertFalse(WiFiScanner._scope_allows(s, 'AP-1'))


if __name__ == '__main__':
    unittest.main()
