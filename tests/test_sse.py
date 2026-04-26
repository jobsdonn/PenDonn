"""Tests for the SSE event-bus state digest helpers (webui.sse)."""

import os
import tempfile
import unittest

from core.database import Database
from webui.sse import (
    _stats_digest,
    _scans_digest,
    _handshakes_digest,
    _networks_digest,
    _passwords_digest,
    _vulns_digest,
    _scope_digest,
    _EVENT_SOURCES,
)


class TestSSEDigests(unittest.TestCase):
    """Each digest fn must:
      1. Be deterministic (same DB state → same digest)
      2. Change when underlying view changes
      3. NOT change for unrelated mutations (avoid spurious events)
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, 'pendonn.db'))

    def tearDown(self):
        # Close any thread-local SQLite connection so Windows lets us delete the file.
        try:
            if hasattr(self.db, '_local') and hasattr(self.db._local, 'conn'):
                self.db._local.conn.close()
                self.db._local.conn = None
        except Exception:
            pass
        self.tmp.cleanup()

    def test_all_event_sources_callable_with_empty_db(self):
        """Smoke: every digest fn must run against a freshly-initialised DB
        without raising."""
        for name, fn in _EVENT_SOURCES.items():
            try:
                d = fn(self.db)
            except Exception as e:
                self.fail(f"Digest {name} raised on empty DB: {e}")
            self.assertIsInstance(d, str)
            self.assertGreater(len(d), 0)

    def test_stats_digest_deterministic(self):
        a = _stats_digest(self.db)
        b = _stats_digest(self.db)
        self.assertEqual(a, b)

    def test_stats_digest_changes_on_network_add(self):
        before = _stats_digest(self.db)
        self.db.add_network('Test', 'AA:BB:CC:DD:EE:01', 6, 'WPA2', -50)
        after = _stats_digest(self.db)
        self.assertNotEqual(before, after)

    def test_scans_digest_changes_on_scan_status_change(self):
        nid = self.db.add_network('Test', 'AA:BB:CC:DD:EE:02', 6, 'WPA2', -50)
        scan_id = self.db.add_scan(nid, 'Test', 'full_enumeration')
        before = _scans_digest(self.db)
        self.db.update_scan(scan_id, 'completed', {'phases': {}}, 0)
        after = _scans_digest(self.db)
        self.assertNotEqual(before, after)

    def test_passwords_digest_changes_on_crack(self):
        nid = self.db.add_network('Test', 'AA:BB:CC:DD:EE:03', 6, 'WPA2', -50)
        hid = self.db.add_handshake(nid, 'AA:BB:CC:DD:EE:03', 'Test', '/tmp/x.cap', 'good')
        before = _passwords_digest(self.db)
        self.db.add_cracked_password(hid, 'Test', 'AA:BB:CC:DD:EE:03',
                                     'p4ssword', 'cowpatty', 1)
        after = _passwords_digest(self.db)
        self.assertNotEqual(before, after)

    def test_scope_digest_changes_on_confirm_and_revoke(self):
        before = _scope_digest(self.db)
        self.db.confirm_scope(['AP-1'], confirmed_by='linus')
        after_confirm = _scope_digest(self.db)
        self.assertNotEqual(before, after_confirm)
        self.db.revoke_scope(revoked_by='linus')
        after_revoke = _scope_digest(self.db)
        self.assertNotEqual(after_confirm, after_revoke)
        # Revoked back to "no active scope" matches the original digest.
        self.assertEqual(before, after_revoke)

    def test_handshakes_digest_unchanged_on_unrelated_mutation(self):
        nid = self.db.add_network('Test', 'AA:BB:CC:DD:EE:04', 6, 'WPA2', -50)
        self.db.add_handshake(nid, 'AA:BB:CC:DD:EE:04', 'Test', '/tmp/x.cap', 'good')
        before = _handshakes_digest(self.db)
        # Add a vuln — nothing handshake-related changed.
        scan_id = self.db.add_scan(nid, 'Test', 'full_enumeration')
        self.db.add_vulnerability(scan_id, '10.0.0.1', 22, 'ssh',
                                  'OpenSSH old version', 'medium',
                                  'OpenSSH 6.x', 'builtin')
        after = _handshakes_digest(self.db)
        self.assertEqual(before, after, "vuln add should not bump handshakes digest")


if __name__ == '__main__':
    unittest.main()
