"""Good Morning Bolt card data for the checkup dashboard.

Fixtures under Data/tests/fixtures/morning/ are sample data, not William's files.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[2]
_core = _repo / "Core"
if str(_core) not in sys.path:
    sys.path.insert(0, str(_core))

from modules import Checkup_Writer as cw  # noqa: E402
from modules import Command_Center as cc  # noqa: E402
from modules import Content_Manager as cm  # noqa: E402
from modules import Researcher as rs  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "morning"


def _isolate(monkeypatch, root: Path) -> None:
    """Point every morning source at `root` so the real Data/ tree stays untouched."""
    content = root / "content"
    business = root / "business"
    briefings = root / "briefings"
    reviews = root / "reviews"
    missions = root / "missions"
    for path in (content, business, briefings, reviews, missions):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cm, "CONTENT_DIR", content)
    monkeypatch.setattr(cm, "BUSINESS_DIR", business)
    monkeypatch.setattr(cm, "BRIEFINGS_DIR", briefings)
    monkeypatch.setattr(cm, "DOCS_REVIEWS", reviews)
    monkeypatch.setattr(cm, "CATALOG_FILE", content / "catalog.json")
    monkeypatch.setattr(cm, "STOREFRONT_FILE", content / "storefront.json")
    monkeypatch.setattr(cm, "SPONSORS_FILE", content / "sponsors.json")
    monkeypatch.setattr(cm, "SOCIAL_FILE", content / "social_connections.json")
    monkeypatch.setattr(cm, "REVIEW_TRACKER", reviews / "review_tracker.json")
    monkeypatch.setattr(cm, "BUSINESS_PLAYBOOK", business / "business-playbook.md")
    monkeypatch.setattr(cm, "ADVANCEMENT_FILE", business / "bolt-advancement.md")
    monkeypatch.setattr(cc, "MISSIONS_DIR", missions)
    monkeypatch.setattr(rs, "RESEARCH_LOG", root / "research_log.jsonl")
    monkeypatch.setattr(cw, "QUEUE_FILE", root / "ready_to_post.json")
    monkeypatch.setattr(cw, "RANKINGS_FILE", root / "rankings.json")
    monkeypatch.setattr(cw, "OUTPUT_FILE", root / "Bolt_data.js")


def _load_sample(root: Path) -> None:
    shutil.copy(FIXTURES / "ready_to_post.json", root / "ready_to_post.json")
    shutil.copy(FIXTURES / "rankings.json", root / "rankings.json")
    shutil.copy(FIXTURES / "catalog.json", root / "content" / "catalog.json")
    shutil.copy(FIXTURES / "research_log.jsonl", root / "research_log.jsonl")
    shutil.copy(
        FIXTURES / "2026-10-16_sample-honest-tech-review.md",
        root / "missions" / "2026-10-16_sample-honest-tech-review.md",
    )
    # Empty on purpose: do not let Content Manager seed the default sponsor list.
    (root / "content" / "sponsors.json").write_text(
        json.dumps({"_sample": True, "prospects": []}) + "\n",
        encoding="utf-8",
    )


def test_fixtures_are_labeled_sample():
    for path in FIXTURES.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "SAMPLE" in text


def test_morning_shape_from_sample_fixtures(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _load_sample(tmp_path)

    morning = cw.gather_morning()

    assert morning["greeting"] == "Good morning, William"
    assert morning["creator"] == "William"
    assert morning["lanes"] == ["game", "tech"]
    assert morning["date"] == date.today().isoformat()
    assert morning["footer"] == "All posts still need your approval."
    assert "generated_at" in morning

    mission = morning["mission"]
    assert mission["empty"] is False
    assert mission["title"] == "Sample honest tech review"
    assert mission["date"] == "2026-10-16"
    mission_age = (date.today() - date.fromisoformat("2026-10-16")).days
    assert mission["stale"] is (mission_age > 7)
    assert mission["actions"] == [
        "Confirm the sample check-in",
        "Stay on the sample week topic",
        "Draft nothing that posts",
    ]
    assert "bolt week" in mission["command"]
    assert "bolt manage next" in mission["command"]

    clips = morning["clips"]
    assert clips["empty"] is False
    assert clips["counts"] == {
        "total": 6,
        "ready": 4,
        "posted": 1,
        "scrapped": 1,
        "other": 0,
    }
    titles = [clip["title"] for clip in clips["clips"]]
    assert titles == [
        "Sample clutch round",
        "Sample headset take",
        "Sample unscored angle",
    ]
    assert clips["clips"][0]["score"] == 88
    assert clips["clips"][0]["file"] == "sample_clutch.mp4"
    assert clips["clips"][0]["platform"] == "TikTok"
    # Score filled from the sample rankings file, not the queue row.
    assert clips["clips"][2]["score"] == 42
    assert clips["clips"][2]["file"] == "sample_unscored.mp4"
    assert "Sample already posted" not in titles
    assert "Sample scrapped take" not in titles
    assert "Sample quiet lobby" not in titles

    research = morning["research"]
    assert research["empty"] is False
    assert research["counts"] == {
        "kept": 1,
        "dropped": 1,
        "pending_c5": 1,
        "blocked_c7": 1,
    }
    assert [row["name"] for row in research["kept"]] == ["Sample Kept Creator"]
    assert research["kept"][0]["platform"] == "YouTube"
    pending_names = [row["name"] for row in research["pending"]]
    assert "Sample Pending Creator" in pending_names
    assert "Sample Maybe Creator" in pending_names
    assert "Sample Dropped Creator" not in pending_names
    assert "Sample Blocked Creator" not in pending_names

    actions = morning["actions"]
    assert actions["empty"] is False
    assert actions["testing"] == 2
    assert actions["items"]
    assert actions["items"][0]["title"] == "Log day-1 notes for Sample Headset"
    assert "bolt manage note" in actions["items"][0]["command"]
    assert actions["advance"]["command"]
    assert actions["lesson"]


def test_morning_empty_when_sources_missing(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    morning = cw.gather_morning()

    assert morning["mission"]["empty"] is True
    assert "bolt mission" in morning["mission"]["hint"]
    assert morning["clips"]["empty"] is True
    assert morning["clips"]["counts"]["total"] == 0
    assert "bolt checkup" in morning["clips"]["hint"]
    assert morning["research"]["empty"] is True
    assert "bolt research find" in morning["research"]["hint"]
    assert morning["actions"]["empty"] is True
    assert "bolt manage add" in morning["actions"]["hint"]
    # Missing catalog must not seed the real content files, and must not
    # invent a sponsor pitch from the default seed list.
    assert morning["actions"]["items"] == []
    assert not (tmp_path / "content" / "sponsors.json").exists()


def test_stale_mission(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mission = tmp_path / "missions" / "2020-01-01_old-sample.md"
    mission.write_text(
        "# SAMPLE — old mission\n\n**Date:** 2020-01-01\n\n**Goal:** Old sample goal\n\n"
        "- [ ] One old step\n",
        encoding="utf-8",
    )

    section = cw.gather_morning()["mission"]

    assert section["stale"] is True
    assert section["title"] == "Old sample goal"
    assert section["date"] == "2020-01-01"


def test_sections_fail_independently(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _load_sample(tmp_path)

    def _boom():
        raise RuntimeError("sample mission unreadable")

    real_read = cw._read_json_document

    def _read(path):
        if path == cw.QUEUE_FILE:
            raise OSError("sample queue unreadable")
        return real_read(path)

    monkeypatch.setattr(cw, "_read_json_document", _read)
    monkeypatch.setattr(cc, "latest_mission", _boom)

    morning = cw.gather_morning()

    assert "error" in morning["mission"]
    assert "sample mission unreadable" in morning["mission"]["error"]
    assert "error" in morning["clips"]
    assert "sample queue unreadable" in morning["clips"]["error"]
    assert morning["research"]["empty"] is False
    assert morning["research"]["kept"][0]["name"] == "Sample Kept Creator"
    assert morning["actions"]["items"][0]["title"] == "Log day-1 notes for Sample Headset"
    assert morning["footer"] == "All posts still need your approval."


def test_gather_stats_includes_morning_and_writes_outside_repo(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _load_sample(tmp_path)

    stats = cw.gather_stats()
    assert "morning" in stats
    assert stats["morning"]["greeting"].startswith("Good morning")

    written = cw.write_data_file(stats)
    assert written == tmp_path / "Bolt_data.js"
    body = written.read_text(encoding="utf-8")
    assert "window.Bolt_DATA" in body
    assert '"morning"' in body
    assert not (_repo / "Data" / "Bolt_data.js").read_text(encoding="utf-8").count("Sample clutch round")
