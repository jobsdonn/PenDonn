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


def _build_app_fixture(tmpdir: str):
    """Wire the FastAPI app against a temp config + temp DB.

    Returns (app, config_path, db_path). Caller is responsible for closing
    app.state.db and removing tmpdir on teardown.
    """
    import json
    config_path = os.path.join(tmpdir, "config.json")
    db_path = os.path.join(tmpdir, "test.db")
    with open(config_path, "w") as f:
        json.dump({
            "system": {"name": "PenDonn", "version": "test", "auto_start": False, "log_level": "WARNING"},
            "wifi": {"monitor_interface": "wlan0", "attack_interface": "wlan1", "management_interface": "wlan2"},
            "whitelist": {"ssids": []},
            "cracking": {"enabled": False, "engines": [], "wordlist_path": "", "auto_start_cracking": False, "max_concurrent_cracks": 1, "john_format": "wpapsk", "hashcat_mode": 22000, "hashcat_rules_dir": "", "use_rules": False, "brute_force": False, "brute_max_length": 4, "session_prefix": "test", "extra_wordlists": []},
            "enumeration": {"enabled": False, "auto_scan_on_crack": False, "nmap_timing": "T2", "port_scan_range": "1-100", "scan_timeout": 60},
            "plugins": {"enabled": False, "directory": "./plugins", "auto_load": False},
            "database": {"path": db_path, "backup_on_export": False},
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

    import webui.app as wa
    from core.database import Database
    wa.CONFIG_PATH = config_path
    wa.config = wa.load_config(config_path)
    wa.app.state.config = wa.config
    wa.app.state.config_path = config_path
    wa.app.state.auth = wa.auth_mod.AuthSettings(wa.config.get("web", {}))
    wa.app.state.db = Database(db_path)
    wa.app.state.templates.env.globals["auth_enabled"] = wa.app.state.auth.enabled
    return wa.app, config_path, db_path


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
        cls.app, cls.config_path, cls.db_path = _build_app_fixture(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.state.db.close_all()
        except Exception:
            pass
        try:
            cls.tmp.cleanup()
        except (PermissionError, OSError):
            pass  # Windows can't unlink while sqlite handle lingers; cosmetic.

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


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestNetworksPage(unittest.TestCase):
    """Networks page — table render, search, sort, whitelist toggle."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.config_path, cls.db_path = _build_app_fixture(cls.tmp.name)
        # Seed some networks so the table has content
        db = cls.app.state.db
        db.add_network("Kjell-Test",   "AA:BB:CC:DD:EE:01", 6,   "WPA2", -45)
        db.add_network("Kjell-Guest",  "AA:BB:CC:DD:EE:02", 11,  "WPA2", -67)
        db.add_network("ancient-AP",   "AA:BB:CC:DD:EE:03", 1,   "WEP",  -82)
        db.add_network("OpenCafe",     "AA:BB:CC:DD:EE:04", 6,   "OPEN", -55)
        # One pre-whitelisted
        db.set_whitelist("AA:BB:CC:DD:EE:01", True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.state.db.close_all()
        except Exception:
            pass
        try:
            cls.tmp.cleanup()
        except (PermissionError, OSError):
            pass

    def setUp(self):
        self.client = TestClient(self.app)
        # Auth in for every test
        r = self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)

    def test_page_renders_and_lists_seeded_networks(self):
        r = self.client.get("/networks")
        self.assertEqual(r.status_code, 200)
        for ssid in ("Kjell-Test", "Kjell-Guest", "ancient-AP", "OpenCafe"):
            self.assertIn(ssid, r.text)

    def test_search_filters_by_ssid(self):
        r = self.client.get("/partials/networks?q=guest")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kjell-Guest", r.text)
        self.assertNotIn("ancient-AP", r.text)

    def test_filter_only_whitelisted(self):
        r = self.client.get("/partials/networks?only=white")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kjell-Test", r.text)
        self.assertNotIn("Kjell-Guest", r.text)

    def test_sort_by_signal_descending(self):
        r = self.client.get("/partials/networks?sort=signal&order=desc")
        self.assertEqual(r.status_code, 200)
        # Strongest signal (-45 = Kjell-Test) should appear before -82 (ancient-AP)
        pos_strong = r.text.find("Kjell-Test")
        pos_weak = r.text.find("ancient-AP")
        self.assertLess(pos_strong, pos_weak)

    def test_sort_validates_column_against_allowlist(self):
        # Bogus sort column falls back to default; never injected
        r = self.client.get("/partials/networks?sort=__bad__")
        self.assertEqual(r.status_code, 200)

    def test_whitelist_toggle_returns_updated_row(self):
        # Currently NOT whitelisted
        r = self.client.post(
            "/partials/networks/AA:BB:CC:DD:EE:02/whitelist",
            data={"whitelisted": "1"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kjell-Guest", r.text)
        self.assertIn("Whitelisted", r.text)
        # Flip back off
        r = self.client.post(
            "/partials/networks/AA:BB:CC:DD:EE:02/whitelist",
            data={"whitelisted": "0"},
        )
        self.assertIn("Add to whitelist", r.text)

    def test_whitelist_toggle_rejects_bad_bssid(self):
        r = self.client.post(
            "/partials/networks/not-a-bssid/whitelist",
            data={"whitelisted": "1"},
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
