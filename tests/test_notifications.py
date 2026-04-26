"""Tests for core.notifications — stdlib only, no live HTTP."""

import json
import time
import unittest
from unittest.mock import patch, MagicMock

from core.notifications import Notifier, _NTFY_PRIORITY


def _disabled_cfg():
    return {'notifications': {'ntfy': {'enabled': False}, 'webhook': {'enabled': False}}}


def _ntfy_cfg(**overrides):
    base = {
        'enabled': True,
        'server': 'https://ntfy.example.com',
        'topic': 'unit-test-topic',
        'token': '',
        'notify_on': {},
    }
    base.update(overrides)
    return {'notifications': {'ntfy': base, 'webhook': {'enabled': False}}}


def _webhook_cfg(**overrides):
    base = {
        'enabled': True,
        'url': 'https://hooks.example.com/in/abc',
        'format': 'json',
        'headers': {},
        'notify_on': {},
    }
    base.update(overrides)
    return {'notifications': {'ntfy': {'enabled': False}, 'webhook': base}}


def _both_cfg():
    return {'notifications': {
        'ntfy': {'enabled': True, 'server': 'https://ntfy.example.com',
                 'topic': 'topic-A', 'token': '', 'notify_on': {}},
        'webhook': {'enabled': True, 'url': 'https://hooks.example.com/in/abc',
                    'headers': {}, 'notify_on': {}},
    }}


class TestNotifierDisabled(unittest.TestCase):
    """When all backends are disabled, Notifier is a no-op."""

    def test_disabled_when_config_says_so(self):
        n = Notifier(_disabled_cfg())
        self.assertFalse(n.enabled)
        n.handshake_captured('ssid', 'AA:BB:CC:DD:EE:FF')
        n.password_cracked('ssid', 'AA:BB:CC:DD:EE:FF', 'cowpatty', 5)
        n.scan_completed('ssid', 0, 0)
        n.vulnerability_found('ssid', 'h', 'high', 'v')

    def test_ntfy_disabled_when_topic_missing(self):
        cfg = _ntfy_cfg(topic='')
        n = Notifier(cfg)
        self.assertFalse(n.enabled)

    def test_webhook_disabled_when_url_missing(self):
        cfg = _webhook_cfg(url='')
        n = Notifier(cfg)
        self.assertFalse(n.enabled)

    def test_no_config_section_safe(self):
        n = Notifier({})
        self.assertFalse(n.enabled)
        n.password_cracked('ssid', 'b', 'cowpatty', 1)


class _BaseEnqueueTest(unittest.TestCase):
    """Shared mocking for HTTP layer."""

    def setUp(self):
        self.urlopen_patcher = patch('core.notifications.urllib.request.urlopen')
        self.mock_urlopen = self.urlopen_patcher.start()
        mock_resp = MagicMock()
        mock_resp.status = 200
        self.mock_urlopen.return_value.__enter__.return_value = mock_resp

    def tearDown(self):
        self.urlopen_patcher.stop()

    def _wait_for_drain(self, n: Notifier, expected_calls: int = 1, timeout: float = 2.0):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.mock_urlopen.call_count >= expected_calls:
                time.sleep(0.05)
                return
            time.sleep(0.02)


class TestNtfyBackend(_BaseEnqueueTest):
    def test_handshake_emits_low_priority(self):
        n = Notifier(_ntfy_cfg())
        n.handshake_captured('test-ssid', 'AA:BB:CC:DD:EE:FF')
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _NTFY_PRIORITY['low'])
        self.assertIn('test-ssid', req.get_header('Title'))
        n.stop()

    def test_crack_emits_high_priority(self):
        n = Notifier(_ntfy_cfg())
        n.password_cracked('ssid', 'b', 'cowpatty', 12)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _NTFY_PRIORITY['high'])
        n.stop()

    def test_critical_vuln_emits_urgent(self):
        n = Notifier(_ntfy_cfg())
        n.vulnerability_found('ssid', '10.0.0.1', 'critical', 'EternalBlue', '')
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Priority'), _NTFY_PRIORITY['urgent'])
        n.stop()

    def test_bearer_token_set(self):
        n = Notifier(_ntfy_cfg(token='tk_secret'))
        n.scan_completed('s', 1, 0)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('Authorization'), 'Bearer tk_secret')
        n.stop()

    def test_per_event_opt_out(self):
        n = Notifier(_ntfy_cfg(notify_on={'handshake': False}))
        n.handshake_captured('s', 'b')
        time.sleep(0.2)
        self.assertFalse(self.mock_urlopen.called)
        n.password_cracked('s', 'b', 'cowpatty', 1)
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        n.stop()


class TestWebhookBackend(_BaseEnqueueTest):
    def test_webhook_posts_json(self):
        n = Notifier(_webhook_cfg())
        n.password_cracked('Customer-AP', 'AA:BB:CC:DD:EE:FF', 'cowpatty', 12)
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.get_header('Content-type'), 'application/json')
        # Decode the JSON payload — must include event/data fields.
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['event'], 'crack')
        self.assertEqual(payload['priority'], 'high')
        self.assertEqual(payload['data']['ssid'], 'Customer-AP')
        self.assertEqual(payload['data']['engine'], 'cowpatty')
        n.stop()

    def test_custom_headers_attached(self):
        n = Notifier(_webhook_cfg(headers={'X-PenDonn': '1', 'Authorization': 'Bearer xyz'}))
        n.scan_completed('s', 1, 0)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('X-pendonn'), '1')
        self.assertEqual(req.get_header('Authorization'), 'Bearer xyz')
        n.stop()

    def test_url_used(self):
        n = Notifier(_webhook_cfg(url='https://example.com/in/zzz'))
        n.handshake_captured('s', 'b')
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, 'https://example.com/in/zzz')
        n.stop()


class TestWebhookFormats(_BaseEnqueueTest):
    """Verify each format produces the shape the destination expects."""

    def test_discord_format_uses_content_and_embed(self):
        n = Notifier(_webhook_cfg(format='discord'))
        n.password_cracked('Customer-AP', 'AA:BB:CC:DD:EE:FF', 'cowpatty', 12)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        # Discord requires content OR embeds — we send both for safety.
        self.assertIn('content', payload)
        self.assertIn('embeds', payload)
        self.assertEqual(len(payload['embeds']), 1)
        embed = payload['embeds'][0]
        self.assertIn('Customer-AP', embed['title'])
        self.assertIn('description', embed)
        # high priority -> orange (0xF59E0B = 16096267)
        self.assertEqual(embed['color'], 0xF59E0B)
        self.assertEqual(payload['username'], 'PenDonn')
        n.stop()

    def test_discord_critical_vuln_is_red(self):
        n = Notifier(_webhook_cfg(format='discord'))
        n.vulnerability_found('AP', '10.0.0.1', 'critical', 'EternalBlue', '')
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['embeds'][0]['color'], 0xEF4444)
        n.stop()

    def test_slack_format_uses_text_and_attachment(self):
        n = Notifier(_webhook_cfg(format='slack'))
        n.password_cracked('AP', 'b', 'cowpatty', 5)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertIn('text', payload)
        self.assertIn('attachments', payload)
        self.assertEqual(payload['attachments'][0]['color'], '#F59E0B')

    def test_teams_format_uses_messagecard(self):
        n = Notifier(_webhook_cfg(format='teams'))
        n.scan_completed('AP', 5, 1)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['@type'], 'MessageCard')
        self.assertEqual(payload['@context'], 'https://schema.org/extensions')
        self.assertIn('themeColor', payload)
        # themeColor is hex without leading #.
        self.assertRegex(payload['themeColor'], r'^[0-9A-F]{6}$')

    def test_unknown_format_falls_back_to_json(self):
        n = Notifier(_webhook_cfg(format='nonsense'))
        n.handshake_captured('s', 'b')
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertIn('event', payload)
        self.assertIn('data', payload)

    def test_autodetect_discord_url(self):
        from core.notifications import _autodetect_webhook_format
        self.assertEqual(_autodetect_webhook_format(
            'https://discord.com/api/webhooks/123/abc'), 'discord')
        self.assertEqual(_autodetect_webhook_format(
            'https://discordapp.com/api/webhooks/123/abc'), 'discord')

    def test_autodetect_slack_url(self):
        from core.notifications import _autodetect_webhook_format
        self.assertEqual(_autodetect_webhook_format(
            'https://hooks.slack.com/services/T1/B2/abc'), 'slack')

    def test_autodetect_teams_url(self):
        from core.notifications import _autodetect_webhook_format
        self.assertEqual(_autodetect_webhook_format(
            'https://acme.webhook.office.com/webhookb2/abc'), 'teams')

    def test_autodetect_unknown_falls_back_to_json(self):
        from core.notifications import _autodetect_webhook_format
        self.assertEqual(_autodetect_webhook_format(
            'https://my-server.example.com/in'), 'json')

    def test_autodetect_used_when_format_not_set(self):
        """If config omits `format`, Notifier autodetects from URL."""
        cfg = {'notifications': {
            'ntfy': {'enabled': False},
            'webhook': {
                'enabled': True,
                'url': 'https://discord.com/api/webhooks/1/x',
                'headers': {}, 'notify_on': {},
                # no `format` key
            },
        }}
        n = Notifier(cfg)
        n.password_cracked('AP', 'b', 'cowpatty', 1)
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        # Discord shape, not generic JSON.
        self.assertIn('embeds', payload)
        self.assertNotIn('event', payload)
        n.stop()


class TestBothBackends(_BaseEnqueueTest):
    def test_both_backends_receive_event(self):
        n = Notifier(_both_cfg())
        n.password_cracked('ssid', 'b', 'cowpatty', 5)
        # Two backends → two HTTP calls.
        self._wait_for_drain(n, expected_calls=2)
        self.assertGreaterEqual(self.mock_urlopen.call_count, 2)
        n.stop()


class TestSendTest(_BaseEnqueueTest):
    def test_test_button_returns_true_when_backend_active(self):
        n = Notifier(_ntfy_cfg())
        self.assertTrue(n.send_test(source='unit-test'))
        self._wait_for_drain(n)
        req = self.mock_urlopen.call_args[0][0]
        self.assertIn('test', req.get_header('Title').lower())
        n.stop()

    def test_test_button_returns_false_when_no_backend(self):
        n = Notifier(_disabled_cfg())
        self.assertFalse(n.send_test(source='unit-test'))

    def test_test_bypasses_notify_on(self):
        # Even with all event types muted, test should still fire.
        n = Notifier(_ntfy_cfg(notify_on={
            'handshake': False, 'crack': False,
            'vulnerability': False, 'scan': False,
        }))
        self.assertTrue(n.send_test())
        self._wait_for_drain(n)
        self.assertTrue(self.mock_urlopen.called)
        n.stop()


class TestNotifierResilience(unittest.TestCase):
    def test_http_error_swallowed(self):
        with patch('core.notifications.urllib.request.urlopen', side_effect=Exception('boom')):
            n = Notifier(_ntfy_cfg())
            n.password_cracked('s', 'b', 'cowpatty', 1)
            time.sleep(0.3)
            n.stop()


if __name__ == '__main__':
    unittest.main()
