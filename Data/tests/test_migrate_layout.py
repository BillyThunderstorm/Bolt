"""Targeted tests for bolt migrate-layout (temp folders only; never touches the real repo)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "Core"))


def _engine():
    spec = importlib.util.spec_from_file_location("ml_test", REPO / "scripts" / "migrate_layout.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "Bolt"
    for d in ("Core/modules", "Data", "Docs", "media/clips", "media/Recordings", "3rd_Party"):
        (r / d).mkdir(parents=True)
    monkeypatch.setenv("BOLT_LAYOUT_TRASH_DIR", str(tmp_path / "Trash"))
    return r


def test_dry_run_touches_nothing(root):
    m = _engine()
    (root / "clip.mp4").write_bytes(b"x")
    before = sorted(p.name for p in root.iterdir())
    ops = m.plan_moves(root)
    assert [o["action"] for o in ops] == ["move"]
    assert "Would move" in m.render_plan(ops, dry_run=True)
    assert sorted(p.name for p in root.iterdir()) == before


def test_folder_rule_moves_into_folder(root):
    m = _engine()
    (root / "clip.mp4").write_bytes(b"x")
    (root / "note.rtf").write_text("hi")
    ops = m.plan_moves(root)
    dsts = {o["name"]: o["dst"] for o in ops}
    assert dsts["clip.mp4"] == str(root / "media/clips/clip.mp4")
    assert dsts["note.rtf"] == str(root / "Docs/scratch/note.rtf")
    res = m.apply(ops, repo_root=root)
    assert res["rc"] == 0 and len(res["done"]) == 2
    assert (root / "media/clips/clip.mp4").read_bytes() == b"x"
    assert (root / "Docs/scratch/note.rtf").exists()


def test_duplicate_trashed_different_skipped(root, tmp_path):
    m = _engine()
    (root / "media/clips/a.mp4").write_bytes(b"same")
    (root / "a.mp4").write_bytes(b"same")
    (root / "media/clips/b.mp4").write_bytes(b"live")
    (root / "b.mp4").write_bytes(b"other")
    ops = {o["name"]: o for o in m.plan_moves(root)}
    assert ops["a.mp4"]["action"] == "trash"
    assert ops["b.mp4"]["action"] == "skip" and ops["b.mp4"]["fix"]
    res = m.apply(list(ops.values()), repo_root=root)
    assert res["rc"] == 1  # a skip is reported
    assert not (root / "a.mp4").exists() and (tmp_path / "Trash" / "a.mp4").exists()
    assert (root / "b.mp4").read_bytes() == b"other"  # untouched
    assert (root / "media/clips/b.mp4").read_bytes() == b"live"  # never overwritten


def test_stale_clip_history_keeps_live(root):
    m = _engine()
    (root / "Data/clip_history.json").write_text('{"live": 1, "x": 2}')
    (root / "clip_history.json").write_text('{"old": 1}')
    ops = m.plan_moves(root)
    assert ops[0]["action"] == "trash"
    m.apply(ops, repo_root=root)
    assert json.loads((root / "Data/clip_history.json").read_text()) == {"live": 1, "x": 2}
    assert not (root / "clip_history.json").exists()


def test_stale_without_live_is_moved(root):
    m = _engine()
    (root / "seen_clips.json").write_text("[]")
    ops = m.plan_moves(root)
    assert ops[0]["action"] == "move"
    m.apply(ops, repo_root=root)
    assert (root / "Data/seen_clips.json").exists()


def test_tidy_empty_only_unknown_empty(root):
    m = _engine()
    (root / "state").mkdir()
    (root / "keepme").mkdir()
    (root / "keepme" / "f.txt").write_text("1")
    assert m.plan_moves(root) == []
    ops = m.plan_moves(root, tidy_empty=True)
    assert [(o["name"], o["action"]) for o in ops] == [("state", "trash-folder")]
    m.apply(ops, repo_root=root)
    assert not (root / "state").exists() and (root / "keepme").exists()
    assert (root / "Data").exists()  # known folders never touched even if empty


def test_apply_logs_and_undo_puts_back(root):
    m = _engine()
    (root / "clip.mp4").write_bytes(b"x")
    (root / "state").mkdir()
    res = m.apply(m.plan_moves(root, tidy_empty=True), repo_root=root)
    rows = m.read_log(root)
    assert {r["run_id"] for r in rows} == {res["run_id"]} and len(rows) == 2
    u = m.undo_last(root)
    assert u["run_id"] == res["run_id"]
    assert (root / "clip.mp4").exists() and not (root / "media/clips/clip.mp4").exists()
    assert (root / "state").is_dir()
    assert m.undo_last(root)["message"] == "Nothing to undo."


def test_never_prompts(root, monkeypatch):
    m = _engine()
    (root / "media/clips/b.mp4").write_bytes(b"live")
    (root / "b.mp4").write_bytes(b"other")
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("prompted")))
    m.apply(m.plan_moves(root), repo_root=root)


def test_wrapper_status_ready_and_run(root, capsys):
    from modules import Migrate_Layout as ML
    st = ML.status(probe=True, root=str(root))
    assert st["readiness"] == "READY" and st["ready"] and st["probe_ok"] and st["layout_clean"]
    (root / "x.wav").write_bytes(b"w")
    r = ML.try_run(root=str(root))
    assert r["ok"] and r["planned_ops"] == 1 and (root / "x.wav").exists()
    r = ML.try_run(apply=True, root=str(root))
    assert r["ok"] and (root / "media/Recordings/x.wav").exists()
    assert ML.status(root=str(root))["last_run"]["steps"] == 1
    assert ML.main(["undo", "--root", str(root)]) == 0
    assert (root / "x.wav").exists()
