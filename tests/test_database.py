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


if __name__ == "__main__":
    unittest.main()
