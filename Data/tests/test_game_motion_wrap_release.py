"""Tests for bolt game / motion / wrap / release (18 Oct 2026). No network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "Core") not in sys.path:
    sys.path.insert(0, str(REPO / "Core"))

from modules import Bolt_Wrap, Game_Refresh, Motion_Detector, Song_Release  # noqa: E402


@pytest.fixture()
def game_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"game": "Wolverine", "x": 1}, indent=2) + "\n")
    mapping = tmp_path / "scene_game_mapping.json"
    mapping.write_text(json.dumps({"live_scene": "Live Scene", "scenes": {"Live Scene": "Wolverine"}}))
    monkeypatch.setattr(Game_Refresh, "_CONFIG", cfg)
    monkeypatch.setattr(Game_Refresh, "_MAPPING", mapping)
    monkeypatch.setattr(Game_Refresh, "_STATE", tmp_path / "game_state.json")
    monkeypatch.delenv("BOLT_GAME_STALE_DAYS", raising=False)
    return cfg, mapping


def test_never_confirmed_is_stale(game_env):
    fr = Game_Refresh.freshness()
    assert fr["stale"] and "never confirmed" in fr["reason"]


def test_old_confirmation_is_stale(game_env):
    fr = Game_Refresh.freshness({"game": "Wolverine", "confirmed_at": "2026-01-01T00:00:00Z"})
    assert fr["stale"] and fr["age_days"] > 7


def test_set_confirms_and_writes_config(game_env):
    cfg, _ = game_env
    r = Game_Refresh.set_game("Ghost of Yotei")
    assert r["ok"] and json.loads(cfg.read_text())["game"] == "Ghost of Yotei"
    assert not Game_Refresh.freshness()["stale"]


def test_pin_wins_over_twitch_but_warns(game_env, monkeypatch):
    cfg, _ = game_env
    monkeypatch.setattr(Game_Refresh, "_twitch_game", lambda timeout=8.0: {"game": "Other Game", "error": ""})
    r = Game_Refresh.refresh()
    assert r["game"] == "Wolverine" and r["resolved_via"] == "obs_mapping_pin"
    assert "Other Game" in r["warning"]
    assert json.loads(cfg.read_text())["game"] == "Wolverine"


def test_unpinned_follows_twitch(game_env, monkeypatch):
    cfg, _ = game_env
    Game_Refresh.unpin()
    monkeypatch.setattr(Game_Refresh, "_twitch_game", lambda timeout=8.0: {"game": "Other Game", "error": ""})
    r = Game_Refresh.refresh(source="stream_start")
    assert r["resolved_via"] == "twitch" and json.loads(cfg.read_text())["game"] == "Other Game"
    assert not Game_Refresh.freshness()["stale"]


def test_twitch_down_keeps_value(game_env, monkeypatch):
    Game_Refresh.unpin()
    monkeypatch.setattr(Game_Refresh, "_twitch_game", lambda timeout=8.0: {"game": "", "error": "down"})
    r = Game_Refresh.refresh()
    assert r["resolved_via"] == "kept" and r["game"] == "Wolverine" and r.get("warning")


def test_status_flags_twitch_drift(game_env, monkeypatch):
    Game_Refresh.unpin()
    Game_Refresh.set_game("Wolverine")
    monkeypatch.setattr(Game_Refresh, "_twitch_game", lambda timeout=8.0: {"game": "Other Game", "error": ""})
    st = Game_Refresh.status(check_twitch=True)
    assert st["readiness"] == "READY" and st["twitch_drift"] and "bolt game refresh" in st["drift_fix"]
    assert not st["stale"]  # confirmed recently, but still the wrong game


def test_status_no_twitch_when_pinned_or_skipped(game_env, monkeypatch):
    def boom(timeout=8.0):
        raise AssertionError("should not call Twitch")
    monkeypatch.setattr(Game_Refresh, "_twitch_game", boom)
    assert Game_Refresh.status(check_twitch=True)["twitch_checked"] is False  # pinned
    Game_Refresh.unpin()
    assert Game_Refresh.status()["twitch_checked"] is False  # default: no network


def test_motion_score_at_baseline():
    rep = {"curve_1hz": [[i, 0.01] for i in range(60)] + [[60, 0.08]]}
    assert Motion_Detector.score_at(rep, 60) > 80
    assert Motion_Detector.score_at(rep, 10) < 20


@pytest.mark.skipif(not Motion_Detector.status()["ready"], reason="no ffmpeg/opencv")
def test_motion_finds_action_window(tmp_path):
    import subprocess

    from modules.FFmpeg_Bin import working_ffmpeg

    vid = tmp_path / "m.mp4"
    # 12 s still, 4 s of noise (high motion), 12 s still
    subprocess.run([working_ffmpeg(), "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=12:r=15",
                    "-f", "lavfi", "-i", "nullsrc=s=320x180:d=4:r=15,geq=random(1)*255:128:128",
                    "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=12:r=15",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p", str(vid)],
                   check=True)
    rep = Motion_Detector.analyze(str(vid), window=2.0, top=3)
    assert rep["segments"], rep
    assert 11 <= rep["segments"][0]["peak"] <= 17


def test_wrap_rank_audio_first():
    from modules.Highlight_Detector import HighlightEvent

    evs = [HighlightEvent(timestamp=100.0, confidence=0.5, score=50.0)]
    motion = {"curve_1hz": [[i, 0.01] for i in range(400)],
              "segments": [{"peak": 300.0, "score": 95.0}]}
    picks = Bolt_Wrap._rank(evs, motion, top=2, vod_len=400)
    assert [p["trigger"] for p in picks] == ["audio_spike", "motion"]


def test_wrap_dir_is_dated_and_unique(tmp_path):
    d = Bolt_Wrap.wrap_dir_for(Path("2026-10-01 19-16-51.mp4"), base=tmp_path)
    assert d.name.endswith("_2026-10-01-19-16-51_wrap")
    d.mkdir()
    assert Bolt_Wrap.wrap_dir_for(Path("2026-10-01 19-16-51.mp4"), base=tmp_path).name.endswith("_wrap-2")


def test_wrap_captions_drawtext_handles_apostrophe_and_percent():
    from modules.Clip_Factory import build_caption_drawtext_filter

    vf = build_caption_drawtext_filter([{"start": 0, "end": 2, "text": "I don't know, 100% sure"}])
    assert "\\'" not in vf  # no escaped straight quote (it splits the ffmpeg chain)
    assert "don\u2019t" in vf and "expansion=none" in vf


def test_whisper_cli_fallback_used_without_module(tmp_path, monkeypatch):
    from modules import Subtitle_Generator as SG

    cli = tmp_path / "whisper"
    cli.write_text("#!/bin/sh\n# from whisper.transcribe import cli\n")
    cli.chmod(0o755)
    monkeypatch.setattr(SG, "_has_module", lambda: False)
    monkeypatch.setenv("WHISPER_CLI", str(cli))
    assert SG.whisper_backend() == f"cli:{cli}"
    assert SG.whisper_available() is True
    monkeypatch.setenv("WHISPER_CLI", str(tmp_path / "missing"))
    monkeypatch.setattr(SG, "_CLI_CANDIDATES", ())
    monkeypatch.setattr(SG.shutil, "which", lambda _n: None)
    assert SG.whisper_backend() is None


def test_release_clean_title():
    assert Song_Release.clean_title("01_Weightless_Tonight (1)") == "Weightless Tonight"
    assert Song_Release.clean_title("Under the Cool Moon") == "Under the Cool Moon"


def test_release_cover_checks(tmp_path):
    from PIL import Image

    good, bad = tmp_path / "cover.jpg", tmp_path / "small.png"
    Image.new("RGB", (3000, 3000)).save(good)
    Image.new("RGB", (1400, 1200)).save(bad)
    assert Song_Release.check_cover(good)["ok"]
    issues = Song_Release.check_cover(bad)["issues"]
    assert any("square" in i for i in issues) and any("too small" in i for i in issues)
    assert not Song_Release.check_cover(None)["ok"]


def test_release_missing_folder_soft_fails(tmp_path):
    r = Song_Release.run(str(tmp_path / "nope"), log=lambda *a: None)
    assert not r["ok"] and r["error"].startswith("Release unavailable:")


def test_release_clean_title_real_names():
    ct = Song_Release.clean_title
    assert ct("01 Sinner") == "Sinner"                       # zero-padded, space only
    assert ct("10 Break Your Spirit", strip_number=True) == "Break Your Spirit"
    assert ct("1-01 Take You", strip_number=True) == "Take You"  # disc-track
    assert ct("06-I-Wont-Fold") == "I Wont Fold"             # hyphen-separated export
    assert ct("Swallow Me Whole-2") == "Swallow Me Whole"    # Finder copy suffix
    assert ct("11 Sinner (Duet)", strip_number=True) == "Sinner (Duet)"
    assert ct("7 Rings") == "7 Rings"                        # real number title survives


def _tone(path, seconds=31):
    import math
    import struct
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        frames = bytearray()
        for i in range(44100 * seconds):
            v = int(8000 * math.sin(2 * math.pi * 440 * i / 44100))
            frames += struct.pack("<hh", v, v)
        wf.writeframes(bytes(frames))


def test_release_dedupes_and_finds_named_cover(tmp_path, monkeypatch):
    src = tmp_path / "Manic Party"
    src.mkdir()
    _tone(src / "01-Take-You.wav")
    (src / "01-Take-You.m4a").write_bytes(b"lossy duplicate")
    _tone(src / "02-Sinner.wav")
    pytest.importorskip("PIL")
    from PIL import Image

    Image.new("RGB", (3000, 3000), (120, 0, 160)).save(src / "The Manic Party.jpg")
    Image.new("RGB", (800, 800)).save(src / "Sinner single.jpg")
    out = tmp_path / "out"
    r = Song_Release.run(str(src), artist="billy_", out=str(out), log=lambda *a: None)
    titles = [t["title"] for t in r["tracks"]]
    assert titles == ["Take You", "Sinner"]
    assert r["tracks"][0]["source_file"].endswith(".wav")
    assert any("skipped duplicate 01-Take-You.m4a" in w for w in r["warnings"])
    assert r["cover"]["ok"] and r["cover"]["path"].endswith("The Manic Party.jpg")
    assert r["ok"] and not r["uploaded"]
    assert (out / "audio" / "01 - Take You.wav").is_file() and (out / "cover.jpg").is_file()
    assert (out / "metadata.csv").read_text().count("billy_") == 2
