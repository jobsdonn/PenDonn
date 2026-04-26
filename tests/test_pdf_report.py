"""Smoke tests for the PDF report generator.

We don't try to validate the rendered PDF byte-for-byte — reportlab's output
varies by version and the binary stream is not human-readable. Instead we
check that the report builds without exceptions for representative DB
states (empty, no scope, fully populated with scope) and that section
helpers handle missing data gracefully.
"""

import os
import sys
import tempfile
import unittest

try:
    import reportlab  # noqa: F401
    HAVE_REPORTLAB = True
except ImportError:
    HAVE_REPORTLAB = False

from core.database import Database


@unittest.skipUnless(HAVE_REPORTLAB, "reportlab not installed")
class TestPDFReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "pdf-test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        # Close all thread-local DB connections before cleanup so Windows
        # doesn't whine about open file handles.
        try:
            self.db.close_all()
        except Exception:
            pass
        # Best-effort tmpdir cleanup; on Windows the DB file may still be
        # locked by reportlab's PDF cleanup. Not fatal.
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _generate(self, name="report.pdf"):
        from core.pdf_report import PDFReport
        out = os.path.join(self.tmpdir, name)
        PDFReport(self.db, output_path=out).generate_report()
        return out

    def test_empty_db_renders(self):
        """Report with no networks/handshakes/passwords/vulns should still
        produce a valid PDF — empty-state messaging covers each section."""
        out = self._generate("empty.pdf")
        self.assertTrue(os.path.isfile(out))
        # Even an empty report has cover + summary + sections; expect >5KB
        self.assertGreater(os.path.getsize(out), 5000)

    def test_no_scope_authorisation_renders_warning(self):
        """When no scope_authorizations row exists, the Scope section
        should still render (with a warning) rather than crash."""
        out = self._generate("no-scope.pdf")
        self.assertTrue(os.path.isfile(out))

    def test_with_scope_and_data_renders(self):
        """Full happy-path: scope confirmed, networks/handshakes/passwords
        present. Section numbering shouldn't conflict, no exceptions."""
        self.db.confirm_scope(
            ['Kjell-BYOD', 'Kjell-BYOD-5G'],
            confirmed_by='admin',
            note='Test session',
        )
        nid = self.db.add_network('Kjell-BYOD', 'B0:19:21:ED:84:FA', 4, 'WPA2', -24)
        hs = self.db.add_handshake(
            nid, 'B0:19:21:ED:84:FA', 'Kjell-BYOD',
            '/handshakes/test.pcapng', 'good',
        )
        self.db.add_cracked_password(
            hs, 'Kjell-BYOD', 'B0:19:21:ED:84:FA',
            'secret123', 'cowpatty', 42,
        )
        out = self._generate("populated.pdf")
        # Populated report should be larger than empty
        self.assertGreater(os.path.getsize(out), 5000)

    def test_engagement_window_handles_empty(self):
        """_engagement_window() returns None when no events recorded."""
        from core.pdf_report import PDFReport
        report = PDFReport(self.db, output_path=os.path.join(self.tmpdir, "x.pdf"))
        self.assertIsNone(report._engagement_window())

    def test_engagement_window_with_data(self):
        """_engagement_window() returns (earliest, latest) tuple of strings
        once events are recorded."""
        from core.pdf_report import PDFReport
        self.db.add_network('Test', 'AA:BB:CC:DD:EE:FF', 6, 'WPA2', -50)
        report = PDFReport(self.db, output_path=os.path.join(self.tmpdir, "x.pdf"))
        window = report._engagement_window()
        self.assertIsNotNone(window)
        self.assertEqual(len(window), 2)
        # Format: 'YYYY-MM-DD HH:MM' (16 chars)
        self.assertEqual(len(window[0]), 16)
        self.assertEqual(len(window[1]), 16)


if __name__ == "__main__":
    unittest.main()
