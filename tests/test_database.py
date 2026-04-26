"""Smoke tests for core.database — covers the methods Phase 1 added/touches.

Uses an in-memory SQLite file under tempdir; no fixtures or external deps.
"""

import os
import tempfile
import unittest

from core.database import Database


class TestAddLog(unittest.TestCase):
    """Regression test for the missing-method bug:
    evil_twin and enumerator call db.add_log(); before Phase 1 the method
    didn't exist, so they crashed on first invocation."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close_all()
        self.tmpdir.cleanup()

    def test_add_log_returns_row_id(self):
        row_id = self.db.add_log("evil_twin", "started attack", "INFO")
        self.assertIsInstance(row_id, int)
        self.assertGreater(row_id, 0)

    def test_add_log_default_level(self):
        # evil_twin sometimes calls without a level — default should be INFO
        self.db.add_log("enumerator", "scan complete")
        rows = self.db.get_logs()
        self.assertEqual(rows[0]["level"], "INFO")

    def test_get_logs_filters_by_module(self):
        self.db.add_log("evil_twin", "msg-a")
        self.db.add_log("enumerator", "msg-b")
        self.db.add_log("evil_twin", "msg-c")
        evil = self.db.get_logs(module="evil_twin")
        self.assertEqual(len(evil), 2)
        self.assertTrue(all(r["module"] == "evil_twin" for r in evil))

    def test_get_logs_filters_by_level(self):
        self.db.add_log("x", "info-msg", "INFO")
        self.db.add_log("x", "warn-msg", "WARNING")
        warns = self.db.get_logs(level="WARNING")
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["message"], "warn-msg")

    def test_get_logs_limit(self):
        for i in range(10):
            self.db.add_log("x", f"msg-{i}")
        rows = self.db.get_logs(limit=3)
        self.assertEqual(len(rows), 3)


class TestRetentionPurge(unittest.TestCase):
    """purge_old_data: verify old rows are removed, recent rows are kept."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close_all()
        self.tmpdir.cleanup()

    def _insert_old_log(self, days_ago: int):
        conn = self.db._ensure_connection()
        conn.execute(
            "INSERT INTO system_logs(module, level, message, timestamp) "
            "VALUES(?, ?, ?, datetime('now', ?))",
            ("test", "INFO", "old", f"-{days_ago} days"),
        )
        conn.commit()

    def test_purge_removes_old_logs_keeps_recent(self):
        # Insert one old log (10 days ago) and one recent (1 day ago)
        self._insert_old_log(10)
        self._insert_old_log(1)
        result = self.db.purge_old_data(system_logs_days=7,
                                        failed_handshakes_days=0,
                                        scans_days=0)
        self.assertEqual(result["logs"], 1)
        remaining = self.db.get_logs()
        self.assertEqual(len(remaining), 1)

    def test_purge_zero_days_skips(self):
        self._insert_old_log(100)
        result = self.db.purge_old_data(system_logs_days=0,
                                        failed_handshakes_days=0,
                                        scans_days=0)
        self.assertEqual(result["logs"], 0)
        self.assertEqual(len(self.db.get_logs()), 1)

    def test_purge_failed_handshakes(self):
        net_id = self.db.add_network("Net", "AA:BB:CC:DD:EE:FF", 6, "WPA2", -50)
        hs_id = self.db.add_handshake(net_id, "AA:BB:CC:DD:EE:FF", "Net",
                                      "/tmp/nonexistent.cap")
        self.db.update_handshake_status(hs_id, "failed")
        conn = self.db._ensure_connection()
        conn.execute(
            "UPDATE handshakes SET capture_date=datetime('now','-40 days') WHERE id=?",
            (hs_id,),
        )
        conn.commit()
        result = self.db.purge_old_data(system_logs_days=0,
                                        failed_handshakes_days=30,
                                        scans_days=0)
        self.assertEqual(result["handshakes"], 1)
        self.assertEqual(self.db.get_all_handshakes(), [])

    def test_cracked_handshake_not_purged(self):
        net_id = self.db.add_network("Net2", "AA:BB:CC:DD:EE:01", 6, "WPA2", -50)
        hs_id = self.db.add_handshake(net_id, "AA:BB:CC:DD:EE:01", "Net2",
                                      "/tmp/ok.cap")
        self.db.update_handshake_status(hs_id, "cracked")
        conn = self.db._ensure_connection()
        conn.execute(
            "UPDATE handshakes SET capture_date=datetime('now','-40 days') WHERE id=?",
            (hs_id,),
        )
        conn.commit()
        # Only failed handshakes should be purged — cracked ones never touched
        result = self.db.purge_old_data(system_logs_days=0,
                                        failed_handshakes_days=30,
                                        scans_days=0)
        self.assertEqual(result["handshakes"], 0)
        self.assertEqual(len(self.db.get_all_handshakes()), 1)


if __name__ == "__main__":
    unittest.main()
