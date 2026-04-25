"""Smoke tests for webui — uses FastAPI's TestClient, skipped if deps missing.

These don't replace browser testing; they verify wiring (auth gating,
templates render, partials are available, login flow round-trips).
"""

import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

from werkzeug.security import generate_password_hash


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed (`pip install -r requirements.txt`)")
class TestWebUISmoke(unittest.TestCase):
    """Spin up the FastAPI app against a temp config + temp DB and hit it.

    Each test gets a fresh TestClient so cookies don't leak between tests
    (the earlier shared-client design caused later tests to inherit a
    logged-in session from an earlier login test, hiding real bugs).
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config_path = os.path.join(cls.tmp.name, "config.json")
        cls.db_path = os.path.join(cls.tmp.name, "test.db")

        # Minimum viable config — only fields the webui actually reads.
        import json
        with open(cls.config_path, "w") as f:
            json.dump({
                "system": {"name": "PenDonn", "version": "test", "auto_start": False, "log_level": "WARNING"},
                "wifi": {"monitor_interface": "wlan0", "attack_interface": "wlan1", "management_interface": "wlan2"},
                "whitelist": {"ssids": []},
                "cracking": {"enabled": False, "engines": [], "wordlist_path": "", "auto_start_cracking": False, "max_concurrent_cracks": 1, "john_format": "wpapsk", "hashcat_mode": 22000, "hashcat_rules_dir": "", "use_rules": False, "brute_force": False, "brute_max_length": 4, "session_prefix": "test", "extra_wordlists": []},
                "enumeration": {"enabled": False, "auto_scan_on_crack": False, "nmap_timing": "T2", "port_scan_range": "1-100", "scan_timeout": 60},
                "plugins": {"enabled": False, "directory": "./plugins", "auto_load": False},
                "database": {"path": cls.db_path, "backup_on_export": False},
                "web": {
                    "host": "127.0.0.1", "port": 8081,
                    "secret_key": "x" * 64,
                    "basic_auth": {
                        "enabled": True,
                        "username": "tester",
                        "password_hash": generate_password_hash("hunter2-correct-horse"),
                    },
                },
                "display": {"enabled": False, "type": "none"},
                "safety": {"enabled": True, "armed_override": False},
            }, f)

        # Build the app once against our temp config. Module-level code in
        # webui.app reads the real config when first imported; we patch
        # state in place so subsequent app.state.* accesses see our config.
        import webui.app as wa
        from core.database import Database
        wa.CONFIG_PATH = cls.config_path
        wa.config = wa.load_config(cls.config_path)
        wa.app.state.config = wa.config
        wa.app.state.config_path = cls.config_path
        wa.app.state.auth = wa.auth_mod.AuthSettings(wa.config.get("web", {}))
        wa.app.state.db = Database(cls.db_path)
        # Templates were instantiated at import time with the real
        # config's auth_enabled value baked into globals — patch it here.
        wa.app.state.templates.env.globals["auth_enabled"] = wa.app.state.auth.enabled
        cls.app = wa.app

    @classmethod
    def tearDownClass(cls):
        # Close the SQLite handle (Windows can't unlink an open file).
        try:
            cls.app.state.db.close_all()
        except Exception:
            pass
        try:
            cls.tmp.cleanup()
        except (PermissionError, OSError):
            # Last-resort: leave the temp dir for the OS to reap. Test
            # already passed — cleanup failure on Windows is cosmetic.
            pass

    def setUp(self):
        # Fresh client per test → no cookie bleed-through between tests.
        self.client = TestClient(self.app)

    def test_health_anonymous_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_login_page_renders_anonymous(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sign in", r.text)
        # Form points at /login
        self.assertIn('action="/login"', r.text)

    def test_dashboard_redirects_when_anonymous(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/login?next=/")

    def test_login_bad_creds_redirects_back(self):
        r = self.client.post(
            "/login",
            data={"username": "tester", "password": "wrong", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        self.assertIn("error=invalid", r.headers["location"])

    def test_login_good_creds_sets_cookie_and_dashboard_renders(self):
        r = self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/")
        # Cookie present
        self.assertIn("pendonn_session", self.client.cookies)
        # Dashboard now renders
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Dashboard", r.text)
        # Stats partial works
        r = self.client.get("/partials/stats")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Networks", r.text)

    def test_htmx_request_gets_401_with_hx_redirect(self):
        r = self.client.get("/partials/stats", headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("hx-redirect"), "/login")

    def test_logout_clears_session(self):
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )
        self.assertIn("pendonn_session", self.client.cookies)
        r = self.client.post("/logout", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        # After logout the session cookie should no longer authenticate.
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 303)


if __name__ == "__main__":
    unittest.main()
