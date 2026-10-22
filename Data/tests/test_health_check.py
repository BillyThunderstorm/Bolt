"""Targeted tests for the quick health check (bolt health). Temp files + mocks only."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Core"))
_cwd = os.getcwd()
spec = importlib.util.spec_from_file_location("bolt_health_engine", REPO / "scripts" / "health_check.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)
os.chdir(_cwd)


def test_env_local_wins_over_env(tmp_path, monkeypatch):
    local = tmp_path / ".env.local"
    base = tmp_path / ".env"
    local.write_text('BOLT_HC_TEST="from-local"\n')
    base.write_text("BOLT_HC_TEST=from-env\nBOLT_HC_ONLY_ENV=yes # comment\n")
    monkeypatch.delenv("BOLT_HC_TEST", raising=False)
    monkeypatch.delenv("BOLT_HC_ONLY_ENV", raising=False)
    read = hc.load_settings([local, base])
    assert read == [".env.local", ".env"]
    assert os.environ["BOLT_HC_TEST"] == "from-local"
    assert os.environ["BOLT_HC_ONLY_ENV"] == "yes"


def test_placeholder_key_not_counted(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "your_xai_key_here")
    assert hc._is_set("XAI_API_KEY") is False
    monkeypatch.setenv("XAI_API_KEY", "xai-realvalue123")
    assert hc._is_set("XAI_API_KEY") is True


def test_missing_ffmpeg_is_fail_with_fix():
    from modules import FFmpeg_Bin

    r = hc.Report()
    with mock.patch.object(FFmpeg_Bin, "working_ffmpeg", return_value=None):
        hc.check_tools(r)
    ff = [c for c in r.all_checks() if c["name"].startswith("ffmpeg")][0]
    assert ff["state"] == "FAIL"
    assert "brew install ffmpeg-full" in ff["fix"]


def test_whisper_cli_counts_as_ok():
    from modules import Subtitle_Generator

    r = hc.Report()
    with mock.patch.object(Subtitle_Generator, "whisper_backend", return_value="cli:/usr/local/bin/whisper"):
        hc.check_tools(r)
    w = [c for c in r.all_checks() if c["name"].startswith("Whisper")][0]
    assert w["state"] == "OK" and "/usr/local/bin/whisper" in w["detail"]


def test_no_ai_at_all_fails(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = hc.Report()
    with mock.patch.object(hc, "_ollama_up", return_value=None):
        hc.check_ai(r)
    states = {c["name"]: c["state"] for c in r.all_checks()}
    assert states["Any AI available"] == "FAIL"
    assert states["Ollama (free, on this Mac)"] == "WARN"


def test_no_network_skips_ollama_line(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = hc.Report()
    with mock.patch.object(hc, "_ollama_up", side_effect=AssertionError("should not ping")):
        hc.check_ai(r, ping_ollama=False)
    names = [c["name"] for c in r.all_checks()]
    assert "Ollama (free, on this Mac)" not in names
    assert "Any AI available" not in names


def test_low_disk_fail_and_warn():
    Usage = type("U", (), {})
    for free_gb, state in ((2, "FAIL"), (10, "WARN"), (100, "OK")):
        u = Usage(); u.total = 1000 * 1024 ** 3; u.free = free_gb * 1024 ** 3
        r = hc.Report()
        with mock.patch.object(hc.shutil, "disk_usage", return_value=u):
            hc.check_disk(r)
        assert r.all_checks()[0]["state"] == state


def test_verdict_and_json_shape(capsys):
    r = hc.Report()
    r.section("X")
    r.add("OK", "a")
    r.add("WARN", "b", "detail", "do this")
    d = hc.report_dict(r, [".env"])
    assert d["ok"] is True and d["verdict"].startswith("READY (with warnings)")
    assert d["problems"][0]["fix"] == "do this"
    r.add("FAIL", "c", "bad", "fix c")
    assert hc.verdict(r.counts()).startswith("NOT READY")
    json.dumps(hc.report_dict(r, []))
