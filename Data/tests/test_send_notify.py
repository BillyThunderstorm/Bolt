"""Targeted tests for Send_Notify (bolt send). Fully mocked: sends nothing."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
from modules import Send_Notify as sn  # noqa: E402


def _ch(sms_ok=True, email_ok=True):
    return {
        "sms": {"ok": sms_ok, "to": "…1234", "fix": "set ALERT_PHONE"},
        "email": {"ok": email_ok, "to": "wi…@x.com", "fix": "set SMTP_PASSWORD"},
    }


class FakeAlerts:
    def __init__(self):
        self.calls = []

    def notify(self, text, **kw):
        self.calls.append((text, kw))
        return {"sms": kw.get("sms"), "email": kw.get("email"), "mac": False, "voice": ""}


def test_empty_message_soft_fails():
    r = sn.try_send("  ")
    assert not r["ok"] and r["error"].startswith("Notify unavailable:")


def test_dry_run_sends_nothing():
    fake = FakeAlerts()
    with mock.patch.object(sn, "_try_import_alerts", return_value=fake), \
         mock.patch.object(sn, "_channel_info", return_value=_ch()):
        r = sn.try_send("hi", dry_run=True)
    assert r["ok"] and r["via"] == "dry-run" and not fake.calls
    assert set(r["would_send"]) == {"sms", "email"}


def test_email_only_and_subject_passed():
    fake = FakeAlerts()
    with mock.patch.object(sn, "_try_import_alerts", return_value=fake), \
         mock.patch.object(sn, "_channel_info", return_value=_ch()):
        r = sn.try_send("hi", subject="Subj", email_only=True)
    assert r["ok"] and r["results"] == {"email": True}
    text, kw = fake.calls[0]
    assert kw["subject"] == "Subj" and kw["email"] and not kw["sms"]
    assert not kw["banner"] and not kw["speak"]


def test_broken_channel_skipped_with_fix():
    fake = FakeAlerts()
    with mock.patch.object(sn, "_try_import_alerts", return_value=fake), \
         mock.patch.object(sn, "_channel_info", return_value=_ch(sms_ok=False)):
        r = sn.try_send("hi")
    assert r["ok"] and r["failed"] == {"sms": "set ALERT_PHONE"}
    assert not fake.calls[0][1]["sms"]


def test_nothing_usable_soft_fails():
    with mock.patch.object(sn, "_try_import_alerts", return_value=FakeAlerts()), \
         mock.patch.object(sn, "_channel_info", return_value=_ch(False, False)):
        r = sn.try_send("hi")
    assert not r["ok"] and "nothing to send to" in r["error"]
