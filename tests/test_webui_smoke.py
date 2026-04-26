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
        # NOTE: the URL path is still /whitelist for back-compat (the
        # field name on the networks row reflects the operator's allowlist
        # — same DB column `is_whitelisted`). UI label is now "In allowlist".
        r = self.client.post(
            "/partials/networks/AA:BB:CC:DD:EE:02/whitelist",
            data={"whitelisted": "1"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kjell-Guest", r.text)
        self.assertIn("In allowlist", r.text)
        # Flip back off
        r = self.client.post(
            "/partials/networks/AA:BB:CC:DD:EE:02/whitelist",
            data={"whitelisted": "0"},
        )
        self.assertIn("Add to allowlist", r.text)

    def test_whitelist_toggle_rejects_bad_bssid(self):
        r = self.client.post(
            "/partials/networks/not-a-bssid/whitelist",
            data={"whitelisted": "1"},
        )
        self.assertEqual(r.status_code, 400)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestHandshakesAndPasswordsPages(unittest.TestCase):
    """Handshakes + cracked passwords tables — render, filter, file-missing handling."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.config_path, cls.db_path = _build_app_fixture(cls.tmp.name)
        db = cls.app.state.db

        # Need a network for the FK; add_handshake takes network_id
        net_id = db.add_network("TargetNet", "AA:BB:CC:DD:EE:01", 6, "WPA2", -50)
        db.add_network("OtherNet", "AA:BB:CC:DD:EE:02", 11, "WPA2", -65)
        other_id = (db.get_network_by_bssid("AA:BB:CC:DD:EE:02") or {}).get("id")

        # Pending: file path that doesn't exist on disk → file_exists=False
        cls.h_pending = db.add_handshake(
            net_id, "AA:BB:CC:DD:EE:01", "TargetNet",
            "/nonexistent/handshake.cap", "pending",
        )
        # Cracked: real file we just create
        real_file = os.path.join(cls.tmp.name, "real_capture.cap")
        with open(real_file, "wb") as f:
            f.write(b"\x00" * 5000)  # ~5KB
        cls.h_cracked = db.add_handshake(
            other_id, "AA:BB:CC:DD:EE:02", "OtherNet", real_file, "cracked",
        )
        db.add_cracked_password(cls.h_cracked, "OtherNet", "AA:BB:CC:DD:EE:02",
                                "supersecret123", "hashcat", 42)

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
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )

    # --- handshakes ---------------------------------------------------------

    def test_handshakes_page_lists_all(self):
        r = self.client.get("/handshakes")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TargetNet", r.text)
        self.assertIn("OtherNet", r.text)
        # Status badges
        self.assertIn("pending", r.text)
        self.assertIn("cracked", r.text)

    def test_handshakes_filter_by_status(self):
        r = self.client.get("/partials/handshakes?status=pending")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TargetNet", r.text)
        self.assertNotIn("OtherNet", r.text)

    def test_handshakes_show_file_missing_label(self):
        r = self.client.get("/handshakes")
        self.assertIn("file missing", r.text)  # for the pending one

    def test_handshakes_show_file_size(self):
        r = self.client.get("/handshakes")
        # 5000 bytes → 4.9K
        self.assertIn("4.9K", r.text)

    # --- passwords ----------------------------------------------------------

    def test_passwords_page_lists_cracked(self):
        r = self.client.get("/passwords")
        self.assertEqual(r.status_code, 200)
        self.assertIn("OtherNet", r.text)
        # Plaintext password is in the rendered HTML (revealed via JS)
        self.assertIn("supersecret123", r.text)
        # Engine + crack time formatted
        self.assertIn("hashcat", r.text)
        self.assertIn("42s", r.text)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestScansAndVulnsPages(unittest.TestCase):
    """Scans and vulnerabilities pages."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.config_path, cls.db_path = _build_app_fixture(cls.tmp.name)
        db = cls.app.state.db
        net_id = db.add_network("Lab1", "AA:BB:CC:DD:EE:01", 6, "WPA2", -50)
        cls.scan_id = db.add_scan(net_id, "Lab1", "full")
        import json as _json
        db.update_scan(cls.scan_id, "completed",
                       {"phases": {"port_scan": {"results": [
                           {"ip": "10.0.0.1", "hostname": "router.lab", "ports": [
                               {"port": 22, "service": "ssh"},
                               {"port": 80, "service": "http"},
                           ]},
                           {"ip": "10.0.0.5", "ports": [{"port": 445, "service": "smb"}]},
                       ]}}}, 3)
        db.add_vulnerability(cls.scan_id, "10.0.0.1", 22, "ssh",
                             "Weak SSH algorithms", "high",
                             "ssh-rsa accepted", "ssh_scanner")
        db.add_vulnerability(cls.scan_id, "10.0.0.1", 80, "http",
                             "Default credentials", "critical",
                             "admin/admin works", "router_scanner")
        db.add_vulnerability(cls.scan_id, "10.0.0.5", 445, "smb",
                             "Anonymous SMB share", "medium",
                             "IPC$ readable", "smb_scanner")

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
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )

    def test_scans_page_renders(self):
        r = self.client.get("/scans")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Lab1", r.text)
        self.assertIn("completed", r.text)
        self.assertIn("3 vulns", r.text)

    def test_scan_detail_endpoint(self):
        r = self.client.get(f"/scans/{self.scan_id}")
        self.assertEqual(r.status_code, 200)
        # Hosts + ports listed
        self.assertIn("10.0.0.1", r.text)
        self.assertIn("router.lab", r.text)
        self.assertIn("ssh", r.text)
        # Vulns embedded too
        self.assertIn("Weak SSH algorithms", r.text)
        self.assertIn("Default credentials", r.text)

    def test_scan_detail_404_for_unknown(self):
        r = self.client.get("/scans/99999")
        self.assertEqual(r.status_code, 404)

    def test_vulnerabilities_page_groups_by_severity(self):
        r = self.client.get("/vulnerabilities")
        self.assertEqual(r.status_code, 200)
        # All three vulns visible
        self.assertIn("Weak SSH algorithms", r.text)
        self.assertIn("Default credentials", r.text)
        self.assertIn("Anonymous SMB share", r.text)
        # KPI tile counts (1 critical, 1 high, 1 medium, 0 low)
        self.assertIn("Critical", r.text)
        self.assertIn("High", r.text)

    def test_vulnerabilities_filter_by_severity(self):
        r = self.client.get("/partials/vulnerabilities?severity=critical")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Default credentials", r.text)
        self.assertNotIn("Weak SSH algorithms", r.text)
        self.assertNotIn("Anonymous SMB share", r.text)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestSystemPage(unittest.TestCase):
    """Logs + service control + database reset."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.config_path, cls.db_path = _build_app_fixture(cls.tmp.name)
        # Seed a few system_logs rows so the recent endpoint has fallback data
        db = cls.app.state.db
        db.add_log("test", "boot complete", "INFO")
        db.add_log("test", "dummy warning", "WARNING")

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
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )

    def test_logs_page_renders(self):
        r = self.client.get("/logs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Logs", r.text)
        # Service tabs present
        self.assertIn("Daemon", r.text)
        self.assertIn("Web", r.text)
        # Danger zone visible
        self.assertIn("Reset database", r.text)

    def test_logs_recent_falls_back_to_system_logs_on_non_linux(self):
        # On Windows dev box, journalctl is missing → falls back to db.get_logs.
        r = self.client.get("/api/logs/recent?service=pendonn&n=20")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["service"], "pendonn")
        self.assertIsInstance(body["lines"], list)
        # Our seeded rows should appear
        joined = "\n".join(body["lines"])
        self.assertIn("boot complete", joined)

    def test_logs_recent_rejects_unknown_service(self):
        r = self.client.get("/api/logs/recent?service=evil")
        self.assertEqual(r.status_code, 400)

    def test_services_partial_renders(self):
        r = self.client.get("/partials/services")
        self.assertEqual(r.status_code, 200)
        self.assertIn("pendonn.service", r.text)
        self.assertIn("pendonn-webui.service", r.text)
        # On non-Linux, the "systemctl unavailable" hint shows
        if not __import__("platform").system() == "Linux":
            self.assertIn("unavailable", r.text)

    def test_service_action_no_systemctl_returns_friendly_message(self):
        # On Windows: action is refused with a friendly partial render
        r = self.client.post("/services/pendonn/restart")
        self.assertEqual(r.status_code, 200)
        # Either the platform-unavailable message rendered, or systemctl
        # ran and we got a real status — both are valid; just check we
        # got the partial back.
        self.assertIn("pendonn.service", r.text)

    def test_service_action_rejects_bad_service(self):
        r = self.client.post("/services/evil/start")
        self.assertEqual(r.status_code, 400)

    def test_service_action_rejects_bad_action(self):
        r = self.client.post("/services/pendonn/launch")
        self.assertEqual(r.status_code, 400)

    def test_reset_database_requires_phrase(self):
        r = self.client.post("/danger/reset-database", data={"confirm_phrase": "no"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("RESET", r.json()["detail"])

    def test_reset_database_with_correct_phrase_truncates_and_backs_up(self):
        db = self.app.state.db
        db.add_network("WillBeGone", "AA:BB:CC:00:00:01", 6, "WPA2", -50)
        self.assertEqual(len(db.get_networks()), 1)

        r = self.client.post("/danger/reset-database",
                             data={"confirm_phrase": "RESET"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn(".bak.", body["backup"])
        self.assertTrue(os.path.isfile(body["backup"]))
        self.assertIn("networks", body["tables_truncated"])

        # Backup contains the row that was wiped from the live DB
        import sqlite3
        b = sqlite3.connect(body["backup"])
        try:
            cnt = b.execute("SELECT COUNT(*) FROM networks").fetchone()[0]
            self.assertEqual(cnt, 1)
        finally:
            b.close()
        # Live DB is empty
        self.assertEqual(len(db.get_networks()), 0)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestSettingsPage(unittest.TestCase):
    """Settings: read-only config viewer + whitelist CRUD."""

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
            pass

    def setUp(self):
        self.client = TestClient(self.app)
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )

    def test_settings_page_renders(self):
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        # Title (Phase 2A rename)
        self.assertIn("Allowlist", r.text)
        self.assertIn("Configuration", r.text)
        # Strict mode toggle present
        self.assertIn("Strict mode", r.text)
        # Safety pills present
        self.assertIn("SSHGuard", r.text)
        self.assertIn("Web auth", r.text)

    def test_secrets_redacted_in_config_dump(self):
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        # The fixture's actual hash and secret_key MUST NOT appear
        self.assertNotIn("hunter2-correct-horse", r.text)  # plaintext
        self.assertNotIn("scrypt:", r.text)                # generated hash prefix
        # The literal 'x'*64 secret_key shouldn't either
        self.assertNotIn("x" * 32, r.text)
        # The "<redacted>" marker should be present somewhere
        self.assertIn("redacted", r.text)

    def test_allowlist_add_then_remove(self):
        r = self.client.post("/partials/allowlist/add", data={"ssid": "MyHome"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("MyHome", r.text)
        # Adding again is a no-op
        r2 = self.client.post("/partials/allowlist/add", data={"ssid": "MyHome"})
        self.assertEqual(r2.status_code, 200)
        # Remove
        r3 = self.client.post("/partials/allowlist/remove", data={"ssid": "MyHome"})
        self.assertEqual(r3.status_code, 200)
        self.assertNotIn("MyHome", r3.text)

    def test_legacy_whitelist_url_still_works(self):
        # Bookmarks / mid-deploy htmx requests using the old path keep working.
        r = self.client.post("/partials/whitelist/add", data={"ssid": "LegacyClient"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("LegacyClient", r.text)
        r = self.client.post("/partials/whitelist/remove", data={"ssid": "LegacyClient"})
        self.assertEqual(r.status_code, 200)

    def test_allowlist_persists_to_overlay_under_new_key(self):
        self.client.post("/partials/allowlist/add", data={"ssid": "PersistMe"})
        overlay = self.config_path + ".local"
        self.assertTrue(os.path.isfile(overlay))
        import json as _json
        with open(overlay) as f:
            data = _json.load(f)
        self.assertIn("PersistMe", data.get("allowlist", {}).get("ssids", []))
        # Old `whitelist` key should NOT be present in the new overlay.
        self.assertNotIn("whitelist", data)

    def test_strict_toggle_persists_and_renders(self):
        # Default: strict=True (text says "ON")
        r = self.client.get("/partials/allowlist")
        self.assertIn("Strict mode", r.text)
        self.assertIn("ON", r.text)
        # Flip off
        r = self.client.post("/partials/allowlist/strict", data={"strict": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("OFF", r.text)
        # Persisted to overlay
        import json as _json
        with open(self.config_path + ".local") as f:
            data = _json.load(f)
        self.assertFalse(data["allowlist"]["strict"])
        # Flip back on
        r = self.client.post("/partials/allowlist/strict", data={"strict": "1"})
        self.assertIn("ON", r.text)

    def test_allowlist_rejects_bad_ssid(self):
        r = self.client.post("/partials/allowlist/add", data={"ssid": "bad\nname"})
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post("/partials/allowlist/add", data={"ssid": ""})
        self.assertEqual(r2.status_code, 400)
        r3 = self.client.post("/partials/allowlist/add", data={"ssid": "a" * 33})
        self.assertEqual(r3.status_code, 400)

    def test_cracking_partial_renders(self):
        r = self.client.get("/partials/cracking")
        self.assertEqual(r.status_code, 200)
        # Engine names present
        for eng in ("cowpatty", "aircrack-ng", "john"):
            self.assertIn(eng, r.text)

    def test_cracking_save_reorders_engines_and_persists(self):
        r = self.client.post("/partials/cracking/save", data={
            "engines": "john,aircrack-ng,cowpatty",
            "wordlist_path": "/usr/share/wordlists/rockyou.txt",
            "extra_wordlists": "",
            "max_concurrent": "2",
            "auto_start": "1",
        })
        self.assertEqual(r.status_code, 200)
        # Template re-rendered with the new order
        pos_john = r.text.find("john")
        pos_air = r.text.find("aircrack-ng")
        pos_cow = r.text.find("cowpatty")
        self.assertLess(pos_john, pos_air)
        self.assertLess(pos_air, pos_cow)
        # Persisted to overlay
        import json as _json
        with open(self.config_path + ".local") as f:
            data = _json.load(f)
        self.assertEqual(data["cracking"]["engines"][0], "john")
        self.assertEqual(data["cracking"]["max_concurrent_cracks"], 2)

    def test_cracking_save_rejects_bad_engine_list(self):
        r = self.client.post("/partials/cracking/save", data={
            "engines": "evil,__bad__",
            "wordlist_path": "/tmp/wl.txt",
            "max_concurrent": "2",
        })
        self.assertEqual(r.status_code, 400)

    def test_cracking_save_rejects_out_of_range_concurrency(self):
        r = self.client.post("/partials/cracking/save", data={
            "engines": "cowpatty",
            "wordlist_path": "/tmp/wl.txt",
            "max_concurrent": "99",
        })
        self.assertEqual(r.status_code, 400)

    def test_cracking_settings_section_on_settings_page(self):
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Cracking", r.text)
        # Partial content present inline
        self.assertIn("Engine order", r.text)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestPluginsPage(unittest.TestCase):
    """Plugins management page — list, toggle."""

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
            pass

    def setUp(self):
        self.client = TestClient(self.app)
        self.client.post(
            "/login",
            data={"username": "tester", "password": "hunter2-correct-horse", "next": "/"},
            follow_redirects=False,
        )

    def test_plugins_page_renders(self):
        r = self.client.get("/plugins")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Plugin registry", r.text)
        # Should show 0 errors count tile and installed count.
        self.assertIn("installed", r.text)

    def test_plugins_nav_item_present_on_dashboard(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/plugins", r.text)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestCaptivePortal(unittest.TestCase):
    """Captive portal endpoints — must be anonymous (auth disabled)."""

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
            pass

    def test_captive_root_anonymous(self):
        # No login — must still serve the portal
        c = TestClient(self.app)
        r = c.get("/captive?ssid=Kjell-Guest")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kjell-Guest", r.text)
        self.assertIn("Sign in to WiFi", r.text)

    def test_captive_authenticate_logs_credential_anonymously(self):
        c = TestClient(self.app)
        r = c.post("/captive/authenticate", data={
            "ssid": "Kjell-Guest", "username": "victim@example.com", "password": "supersecret",
        })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertIn("redirect", body)
        # The credential should land in system_logs (no EvilTwin instance in tests)
        logs = self.app.state.db.get_logs(module="captive_portal")
        self.assertTrue(any("victim@example.com" in (l.get("message") or "") for l in logs))


if __name__ == "__main__":
    unittest.main()
