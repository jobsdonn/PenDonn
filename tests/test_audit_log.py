"""Tests for the audit log database API."""

import os
import tempfile
import unittest

from core.database import Database


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, 'pendonn.db'))

    def tearDown(self):
        try:
            if hasattr(self.db, '_local') and hasattr(self.db._local, 'conn'):
                self.db._local.conn.close()
                self.db._local.conn = None
        except Exception:
            pass
        self.tmp.cleanup()

    def test_add_returns_row_id(self):
        rid = self.db.add_audit_log(
            action='scope.confirm',
            actor='linus',
            target='AP-1,AP-2',
        )
        self.assertGreater(rid, 0)

    def test_get_returns_newest_first(self):
        self.db.add_audit_log(action='allowlist.add', actor='alice', target='AP-1')
        self.db.add_audit_log(action='allowlist.add', actor='bob', target='AP-2')
        rows = self.db.get_audit_log()
        self.assertEqual(len(rows), 2)
        # Newest first.
        self.assertEqual(rows[0]['actor'], 'bob')
        self.assertEqual(rows[1]['actor'], 'alice')

    def test_filter_by_action_prefix(self):
        self.db.add_audit_log(action='login.success', actor='linus')
        self.db.add_audit_log(action='login.failure', actor='attacker')
        self.db.add_audit_log(action='allowlist.add', actor='linus', target='AP-1')

        login = self.db.get_audit_log(action_prefix='login.')
        self.assertEqual(len(login), 2)
        self.assertTrue(all(r['action'].startswith('login.') for r in login))

        only_success = self.db.get_audit_log(action_prefix='login.success')
        self.assertEqual(len(only_success), 1)
        self.assertEqual(only_success[0]['actor'], 'linus')

    def test_filter_by_actor(self):
        self.db.add_audit_log(action='login.success', actor='linus')
        self.db.add_audit_log(action='login.failure', actor='attacker')
        rows = self.db.get_audit_log(actor='linus')
        self.assertEqual(len(rows), 1)

    def test_details_roundtrip_through_json(self):
        self.db.add_audit_log(
            action='scope.confirm',
            actor='linus',
            details={'ssids': ['AP-1', 'AP-2'], 'note': 'engagement #42'},
        )
        rows = self.db.get_audit_log()
        self.assertIsInstance(rows[0]['details_parsed'], dict)
        self.assertEqual(rows[0]['details_parsed']['ssids'], ['AP-1', 'AP-2'])
        self.assertEqual(rows[0]['details_parsed']['note'], 'engagement #42')

    def test_no_details_means_none(self):
        self.db.add_audit_log(action='login.logout', actor='linus')
        rows = self.db.get_audit_log()
        self.assertIsNone(rows[0]['details_parsed'])

    def test_limit_caps_results(self):
        for i in range(10):
            self.db.add_audit_log(action='allowlist.add', actor='linus', target=f'AP-{i}')
        rows = self.db.get_audit_log(limit=3)
        self.assertEqual(len(rows), 3)

    def test_add_failure_does_not_raise(self):
        """add_audit_log must be best-effort — never break the caller."""
        # Force a failure by closing the DB after init.
        try:
            if hasattr(self.db._local, 'conn'):
                self.db._local.conn.close()
                self.db._local.conn = None
        except Exception:
            pass
        # Re-initialize for a clean state and then close again to simulate failure.
        self.db._local = type('L', (), {})()
        self.db._local.conn = None
        # First add should reconnect; not really a failure path. Drop the
        # table to force a real error.
        conn = self.db.connect()
        conn.execute('DROP TABLE audit_log')
        conn.commit()
        # Now add — should swallow the OperationalError.
        rid = self.db.add_audit_log(action='test.action')
        self.assertEqual(rid, 0)

    def test_source_ip_recorded(self):
        self.db.add_audit_log(
            action='login.success',
            actor='linus',
            source_ip='192.168.0.42',
        )
        rows = self.db.get_audit_log()
        self.assertEqual(rows[0]['source_ip'], '192.168.0.42')


if __name__ == '__main__':
    unittest.main()
