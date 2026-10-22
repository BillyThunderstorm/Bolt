"""Bolt_Alerts — ElevenLabs first, Nathan (Enhanced) fallback, never Siri "Voice 3".

All tests use mocks + temp files: nothing is shown, spoken, texted or emailed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Bolt_Alerts as alerts
from modules import Bolt_Voice as voice

_CLEAN_ENV = {
    "Bolt_VOICE": "",
    "BOLT_VOICE": "",
    "Bolt_VOICE_MUTE": "false",
    "BOLT_ALERT_SPEAK": "true",
    "BOLT_ALERT_MAC": "true",
    "Bolt_TTS_PROVIDER": "elevenlabs",
    "ELEVENLABS_API_KEY": "test-key",
    "ELEVENLABS_VOICE_ID": "test-voice",
}


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "alerts.jsonl"
        self._patches = [
            patch.object(alerts, "_load_alert_env", lambda: None),
            patch.object(alerts, "_ALERT_LOG", self.log),
            patch.dict(os.environ, _CLEAN_ENV),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()


class NeverSiriTests(_Base):
    def test_siri_voice_names_swapped_for_nathan(self):
        for bad in ("Voice 3", "voice 1", "Siri Voice 2", "Siri"):
            with patch.dict(os.environ, {"Bolt_VOICE": bad}):
                self.assertEqual(alerts.fallback_voice(), "Nathan (Enhanced)", bad)

    def test_default_fallback_is_nathan(self):
        self.assertEqual(alerts.fallback_voice(), "Nathan (Enhanced)")

    def test_bolt_voice_macos_say_never_passes_voice_3(self):
        with patch.object(voice, "MUTED", False), patch.object(
            voice, "VOICE", "Voice 3"
        ), patch("modules.Bolt_Voice.subprocess.run") as run:
            run.return_value = None
            ok = voice.macos_say("Briefing is ready")
        self.assertTrue(ok)
        args = run.call_args[0][0]
        self.assertEqual(args[:3], ["say", "-v", "Nathan (Enhanced)"])
        self.assertNotIn("Voice 3", args)


class SpeakOrderTests(_Base):
    def test_elevenlabs_first(self):
        with patch.object(alerts, "_speak_elevenlabs", return_value=True) as el, patch(
            "modules.Bolt_Alerts.subprocess.run"
        ) as run:
            who = alerts._speak_alert("Budget at 50 percent")
        self.assertEqual(who, "elevenlabs")
        el.assert_called_once()
        run.assert_not_called()

    def test_falls_back_to_nathan_when_elevenlabs_fails(self):
        with patch.object(alerts, "_speak_elevenlabs", return_value=False), patch(
            "modules.Bolt_Alerts.subprocess.run"
        ) as run:
            run.return_value = MagicMock(returncode=0)
            who = alerts._speak_alert("Budget at 50 percent")
        self.assertEqual(who, "Nathan (Enhanced)")
        args = run.call_args[0][0]
        self.assertEqual(args[:3], ["say", "-v", "Nathan (Enhanced)"])

    def test_no_elevenlabs_key_goes_straight_to_nathan(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), patch.object(
            alerts, "_speak_elevenlabs"
        ) as el, patch("modules.Bolt_Alerts.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            who = alerts._speak_alert("hi")
        el.assert_not_called()
        self.assertEqual(who, "Nathan (Enhanced)")

    def test_muted_says_nothing(self):
        with patch.dict(os.environ, {"Bolt_VOICE_MUTE": "true"}), patch.object(
            alerts, "_speak_elevenlabs"
        ) as el, patch("modules.Bolt_Alerts.subprocess.run") as run:
            self.assertEqual(alerts._speak_alert("hi"), "")
        el.assert_not_called()
        run.assert_not_called()

    def test_banner_can_skip_speech(self):
        with patch.object(alerts, "_speak_alert") as speak, patch(
            "modules.Bolt_Alerts.subprocess.run"
        ) as run:
            run.return_value = MagicMock(returncode=0)
            alerts.mac_banner("Bolt", "hello", speak=False)
        speak.assert_not_called()


class FanoutTests(_Base):
    def test_channel_flags(self):
        c = alerts._parse_channels(["test", "--no-sms"])
        self.assertEqual(c, {"mac": True, "voice": True, "sms": False, "email": True})
        c = alerts._parse_channels(["test", "--only", "mac,email"])
        self.assertEqual(c, {"mac": True, "voice": False, "sms": False, "email": True})
        self.assertEqual(alerts._strip_channel_args(["send", "--only", "mac", "hi", "there"]), ["send", "hi", "there"])

    def test_notify_respects_channels_and_logs(self):
        with patch.object(alerts, "mac_banner", return_value=True) as banner, patch.object(
            alerts, "_speak_alert", return_value="elevenlabs"
        ), patch.object(alerts, "send_sms") as sms, patch.object(
            alerts, "send_email", return_value=True
        ) as email:
            res = alerts.notify("hello", title="Bolt test", sms=False)
        banner.assert_called_once_with("Bolt test", "hello", speak=False)
        sms.assert_not_called()
        email.assert_called_once()
        self.assertEqual(res, {"mac": True, "voice": "elevenlabs", "sms": False, "email": True})
        row = json.loads(self.log.read_text().strip())
        self.assertEqual(row["title"], "Bolt test")
        self.assertNotIn("hello", self.log.read_text())  # bodies are not logged

    def test_try_test_reports_failed_channel(self):
        with patch.object(alerts, "status", return_value={"ready": True, "readiness": "READY"}), patch.object(
            alerts, "notify", return_value={"mac": True, "voice": "Nathan (Enhanced)", "sms": False, "email": False}
        ), patch("sys.stdout") as _out:
            alerts.try_test(as_json=False, chosen={"mac": True, "voice": True, "sms": False, "email": True})


class ProbeTests(_Base):
    def test_smtp_probe_auth_error_gives_fix(self):
        import smtplib

        smtp = MagicMock()
        smtp.__enter__.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
        with patch.dict(os.environ, {"SMTP_USERNAME": "u", "SMTP_PASSWORD": "p"}), patch(
            "smtplib.SMTP", return_value=smtp
        ):
            res = alerts._probe_smtp()
        self.assertFalse(res["ok"])
        self.assertIn("App Password", res["detail"])

    def test_smtp_probe_never_sends(self):
        smtp = MagicMock()
        with patch.dict(os.environ, {"SMTP_USERNAME": "u", "SMTP_PASSWORD": "p"}), patch(
            "smtplib.SMTP", return_value=smtp
        ):
            res = alerts._probe_smtp()
        self.assertTrue(res["ok"])
        smtp.__enter__.return_value.sendmail.assert_not_called()
        smtp.__enter__.return_value.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
