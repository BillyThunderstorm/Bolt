"""Targeted tests for Learning_Notes (bolt learning). Uses a temp folder only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
import modules.Learning_Notes as LN  # noqa: E402


def _setup(tmp_path, monkeypatch):
    d = tmp_path / "learning"
    d.mkdir()
    (d / "_TEMPLATE.md").write_text("# Ch0X — [Chapter Title]\n*Captured: YYYY-MM-DD | Source: [x]*\n\n## The core idea\n")
    (d / "ch01-intro.md").write_text("# Ch01 — Intro\n*Captured: 2026-01-01 | Source: book*\nTokens are pieces of text.\n")
    (d / "ch02-a.md").write_text("# Ch02 — A\nsoftmax turns scores into weights\n")
    (d / "ch02-b.md").write_text("# Ch02 — B\nnothing here\n")
    monkeypatch.setattr(LN, "_LEARNING", d)
    monkeypatch.setattr(LN, "_open_file", lambda p: None)
    return d


def test_status_ready(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert LN.status()["chapter_count"] == 3


def test_number_resolve_and_ambiguous(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert LN.resolve_note("1").name == "ch01-intro.md"
    assert LN.resolve_note("2") is None


def test_search(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)
    LN.search_notes("softmax weights", as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["match_count"] == 1 and out["matches"][0]["stem"] == "ch02-a"


def test_new_never_overwrites(tmp_path, monkeypatch, capsys):
    d = _setup(tmp_path, monkeypatch)
    LN.new_note("Embeddings", source="video", as_json=True)
    out = json.loads(capsys.readouterr().out)
    p = Path(out["path"])
    assert p.name == "ch03-embeddings.md"
    text = p.read_text()
    assert text.startswith("# Ch03 — Embeddings") and "Source: video" in text
    p.write_text("mine")
    LN.new_note("Ch03 — Embeddings", as_json=True)
    out2 = json.loads(capsys.readouterr().out)
    assert out2["ok"] is False and p.read_text() == "mine"
    assert (d / "_TEMPLATE.md").read_text().startswith("# Ch0X")
