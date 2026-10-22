"""Targeted tests for ICloud_Sync (bolt icloud). Temp folders only — never touches iCloud."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
import modules.ICloud_Sync as IC  # noqa: E402


def _setup(tmp_path, monkeypatch):
    src = tmp_path / "Bolt"
    (src / "Core" / "modules").mkdir(parents=True)
    (src / "Core" / "modules" / "a.py").write_text("print('a')\n")
    (src / "Core" / "credentials.json").write_text("{}")
    (src / "README.md").write_text("hi\n")
    (src / ".env").write_text("SECRET=1\n")
    (src / ".env.local").write_text("SECRET=2\n")
    (src / ".env.example").write_text("SECRET=\n")
    (src / "Data").mkdir()
    (src / "Data" / "gmail_token.json").write_text("{}")
    (src / "Data" / "queue.json").write_text("[]")
    (src / "Data" / "backups").mkdir()
    (src / "Data" / "backups" / "old.json").write_text("x")
    for d in ("recordings", "media", ".git", ".venv", "node_modules", "logs", "Core/__pycache__"):
        (src / d).mkdir(parents=True, exist_ok=True)
        (src / d / "f.bin").write_text("x")
    (src / "App").mkdir()
    (src / "App" / "ring.mov").write_text("video")
    dst = tmp_path / "iCloud" / "Bolt"
    logs = tmp_path / "state"
    monkeypatch.setattr(IC, "_LOG", logs / "icloud_sync.jsonl")
    monkeypatch.setattr(IC, "_STATE", logs / "icloud_sync_state.json")
    monkeypatch.setenv("BOLT_ICLOUD_TRASH_DIR", str(tmp_path / "Trash"))
    return src, dst


def test_plan_skips_secrets_media_and_junk(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    p = IC.plan(source=src, dest=dst)
    paths = sorted(r["path"] for r in p["copy"])
    assert paths == [".env.example", "Core/modules/a.py", "Data/queue.json", "README.md"]
    assert p["skipped"]["secret"]["files"] == 4  # .env, .env.local, credentials, token
    assert "media" in p["skipped"] and "excluded folder" in p["skipped"]
    assert not dst.exists()  # plan is read-only


def test_sync_copies_and_logs(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    res = IC.sync(source=src, dest=dst, check_space=False)
    assert res["ok"] and len(res["copied"]) == 4
    assert (dst / "Core/modules/a.py").read_text() == "print('a')\n"
    assert not (dst / ".env").exists() and not (dst / "recordings").exists()
    rows = [json.loads(line) for line in IC._LOG.read_text().splitlines()]
    assert rows[-1]["event"] == "summary" and rows[-1]["copied"] == 4
    assert IC._last_run()["copied"] == 4
    again = IC.sync(source=src, dest=dst, check_space=False)
    assert again["summary"]["copied"] == 0 and again["summary"]["unchanged"] == 4


def test_never_overwrites_changed_icloud_file(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    IC.sync(source=src, dest=dst, check_space=False)
    (dst / "README.md").write_text("edited on Magneto\n")
    (src / "README.md").write_text("new on Goddess\n")
    res = IC.sync(source=src, dest=dst, check_space=False)
    assert (dst / "README.md").read_text() == "edited on Magneto\n"
    assert "README.md" in res["summary"]["conflicts"]


def test_refresh_untouched_copy_trashes_old(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    IC.sync(source=src, dest=dst, check_space=False)
    (src / "Core/modules/a.py").write_text("print('b')\n")
    res = IC.sync(source=src, dest=dst, check_space=False)
    assert res["refreshed"] == ["Core/modules/a.py"]
    assert (dst / "Core/modules/a.py").read_text() == "print('b')\n"
    assert any((tmp_path / "Trash").iterdir())


def test_size_limit_refuses(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    (src / "Data" / "big.json").write_bytes(b"0" * (2 * 1048576))
    res = IC.sync(source=src, dest=dst, max_mb=1, check_space=False)
    assert not res["ok"] and "safety limit" in res["error"] and not dst.exists()


def test_only_scope(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    p = IC.plan(source=src, dest=dst, only=["Core"])
    assert [r["path"] for r in p["copy"]] == ["Core/modules/a.py"]


def test_legacy_scripts_never_run():
    out = IC.try_run(script="shared", apply=True, dry_run=False)
    assert out["ok"] and "never runs" in out["report"]


def test_status_soft_fail_without_icloud(tmp_path, monkeypatch):
    monkeypatch.setattr(IC, "_icloud_root", lambda: tmp_path / "nope")
    st = IC.status()
    if st["darwin"]:
        assert not st["ready"] and st["error"].startswith(IC._SOFT)
        assert "iCloud Drive ON" in st["error"]
