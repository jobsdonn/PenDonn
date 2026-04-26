"""Tests for core.notifications — stdlib only, no live HTTP."""

import time
import unittest
from unittest.mock import patch, MagicMock

from core.notifications import Notifier, _PRIORITY


def _disabled_cfg():
    return {'notifications': {'ntfy': {'enabled': False}}}


def _enabled_cfg(**overrides):
    base = {
        'enabled': True,
        'server': 'https://ntfy.example.com',
        'topic': 'unit-test-topic',
        'token': '',
        'notify_on': {},
    }
    base.update(overrides)
    return {'notifications': {'ntfy': base}}


class TestNotifierDisabled(unittest.TestCase):
    """When disabled, Notifier should be a no-op for everything."""

    def test_disabled_when_config_says_so(self):
        n = Notifier(_disabled_cfg())
        self.assertFalse(n.enabled)
        # Calls should not raise.
        n.handshake_captured('ssid', 'AA:BB:CC:DD:EE:FF')
        n.password_cracked('ssid', 'AA:BB:CC:DD:EE:FF', 'cowpatty', 5)
        n.scan_completed('ssid', 0, 0)
        n.vulnerability_found('ssid', 'h', 'high', 'v')

    def test_disabled_when_topic_missing(self):
        cfg = _enabled_cfg(topic='')
        n = Notifier(cfg)
        # Auto-disabled because topic is empty.
        self.assertFalse(n.enabled)

    def test_no_config_section_safe(self):
        """Config without notifications.* should still produce a working no-op."""
        n = Notifier({})
        self.assertFalse(n.enabled)
        n.password_cracked('ssid', 'b', 'cowpatty', 1)


class TestNotifierEnqueue(unittest.TestCase):
    """When enabled, events should reach the worker queue. We mock the
    HTTP call so no real traffic leaves the test."""

    def setUp(self):
        # Patch urlopen at the module level so worker thread doesn't hit network.
        self.urlopen_patcher = patch('core.notifications.urllib.request.urlopen')
        self.mock_urlopen = self.urlopen_patcher.start()
        # Mock context manager response.
        mock_resp = MagicMock()
        mock_resp.status = 200
        self.mock_urlopen.return_value.__enter__.return_value = mock_resp

    def tearDown(self):
        self.urlopen_patcher.stop()

    def _wait_for_drain(self, n: Notifier, timeout: float = 2.0):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if n._queue.empty() and self.mock_urlopen.called:
                # Give worker a moment to finish the in-flight request.
                time.sleep(0.05)
                return
            time.sleep(0.02)

    def test_handshake_captured_emits_low_priority(self):
        n = Notifier(_enabled_cfg())
        n.handshake_captured('test-ssid', 'AA:BB:CC:DD:EE:FF')
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _PRIORITY['low'])
        self.assertIn('test-ssid', req.get_header('Title'))
        n.stop()

    def test_password_cracked_emits_high_priority(self):
        n = Notifier(_enabled_cfg())
        n.password_cracked('ssid', 'b', 'cowpatty', 12)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _PRIORITY['high'])
        n.stop()

    def test_critical_vuln_emits_urgent(self):
        n = Notifier(_enabled_cfg())
        n.vulnerability_found('ssid', '10.0.0.1', 'critical', 'EternalBlue', '')
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _PRIORITY['urgent'])
        n.stop()

    def test_token_is_passed_as_bearer_when_set(self):
        n = Notifier(_enabled_cfg(token='tk_secret'))
        n.scan_completed('s', 1, 0)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Authorization'), 'Bearer tk_secret')
        n.stop()

    def test_per_event_opt_out(self):
        n = Notifier(_enabled_cfg(notify_on={'handshake': False}))
        n.handshake_captured('s', 'b')
        # Give worker a beat — but no event should have been enqueued.
        time.sleep(0.2)
        self.assertFalse(self.mock_urlopen.called)
        # Other events still fire.
        n.password_cracked('s', 'b', 'cowpatty', 1)
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        n.stop()


class TestNotifierResilience(unittest.TestCase):
    """A failing ntfy server must not crash the daemon."""

    def test_http_error_swallowed(self):
        with patch('core.notifications.urllib.request.urlopen', side_effect=Exception('boom')):
            n = Notifier(_enabled_cfg())
            # This should not raise even though the worker thread hits an
            # exception trying to deliver.
            n.password_cracked('s', 'b', 'cowpatty', 1)
            time.sleep(0.3)
            n.stop()


if __name__ == '__main__':
    unittest.main()
