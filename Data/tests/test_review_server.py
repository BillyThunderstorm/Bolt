"""Clip review board server. Sample fixtures only — William's Data/ stays untouched."""

from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import sys
import threading
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[2]
_core = _repo / "Core"
_scripts = _repo / "scripts"
for _path in (_core, _scripts):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import review_server  # noqa: E402
from modules import Checkup_Writer as checkup  # noqa: E402
from modules import Peak_Hour_Notifier as peak  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "review"
GUARDED = [
    _repo / "Data" / "decision_model.json",
    _repo / "Data" / "unified_memory.jsonl",
    _repo / "Data" / "source_registry.json",
    _repo / "Data" / "MEMORY.md",
    _repo / "Data" / "memory_index.json",
    _repo / "Data" / "Bolt_data.js",
    _repo / "Data" / "post_rejections.jsonl",
    _repo / "Data" / "ready_to_post.json",
]
BANNED_WRITES = (
    "approve_next_clip",
    "post_now",
    "mark_posted",
    "process_auto_post_queue",
)


def _digest() -> dict[str, str]:
    found = {}
    for path in GUARDED:
        if not path.exists():
            found[str(path)] = "missing"
            continue
        found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


@pytest.fixture(autouse=True)
def _real_data_untouched():
    before = _digest()
    yield
    assert _digest() == before


@pytest.fixture
def review_root(tmp_path, monkeypatch):
    root = tmp_path / "review"
    shutil.copytree(FIXTURES, root)
    for obj, name, value in review_server.fixture_bindings(root):
        monkeypatch.setattr(obj, name, value)
    memory = root / "MEMORY.md"
    if not memory.exists():
        memory.write_text("# SAMPLE\n\n## Recent Notes\n", encoding="utf-8")
    monkeypatch.setattr(peak, "_send_discord", lambda message: None)
    return root


@pytest.fixture
def board(review_root):
    httpd = review_server.create_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=3)


def _request(httpd, method, path, *, token=None, body=None, host=None, origin=None):
    port = httpd.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-Bolt-Review-Token"] = token
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    status = resp.status
    conn.close()
    return status, raw


def _json_body(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


def _queue(root: Path) -> dict:
    return json.loads((root / "ready_to_post.json").read_text(encoding="utf-8"))


def _clip(root: Path, clip_id: str) -> dict:
    for row in _queue(root)["clips"]:
        if row["id"] == clip_id:
            return row
    raise AssertionError(clip_id)


def test_fixtures_are_labeled_sample():
    for path in FIXTURES.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".jpg", ".jpeg", ".mp4"}:
            assert path.stat().st_size > 0
            continue
        assert "SAMPLE" in path.read_text(encoding="utf-8")


def test_server_source_has_no_posting_verbs():
    text = (_scripts / "review_server.py").read_text(encoding="utf-8")
    for name in BANNED_WRITES:
        assert name not in text


def test_main_rejects_public_host():
    assert review_server.main(["--host", "0.0.0.0", "--no-open", "--port", "9"]) == 2


def test_gather_review_shape_and_mac_thumbnail(review_root):
    board = checkup.gather_review()
    assert board["empty"] is False
    assert board["counts"] == {
        "total": 7,
        "ready": 4,
        "held": 1,
        "posted": 1,
        "scrapped": 1,
        "other": 0,
        "actionable": 3,
    }
    ids = [clip["id"] for clip in board["clips"]]
    assert ids[:3] == ["a11ce001", "b22ce002", "g77ce007"]
    first = board["clips"][0]
    assert first["title"] == "SAMPLE #007FirstLight"
    assert first["score"] == 91
    assert first["trigger"] == "audio_spike"
    assert first["clip_index"] == 1
    assert first["file_exists"] is True
    assert first["has_thumbnail"] is True
    assert first["ghost"] is False
    assert first["pill"] == "ready"
    ghost = next(clip for clip in board["clips"] if clip["id"] == "c33ce003")
    assert ghost["ghost"] is True
    assert ghost["file_exists"] is False
    assert ghost["has_thumbnail"] is False
    held = next(clip for clip in board["clips"] if clip["id"] == "d44ce004")
    assert held["pill"] == "held"
    assert held["hold_reason"] == "boring"
    assert held["has_thumbnail"] is False
    mid = next(clip for clip in board["clips"] if clip["id"] == "g77ce007")
    assert mid["pill"] == "queued"
    assert mid["actionable"] is True
    assert [clip["id"] for clip in board["top"]] == ["a11ce001", "b22ce002", "g77ce007"]
    thumb = checkup.thumbnail_for_clip(_clip(review_root, "a11ce001")["clip_path"])
    assert thumb is not None
    assert thumb.suffix == ".jpg"
    assert thumb.resolve().is_relative_to(review_root.resolve())


def test_score_falls_back_to_rankings(review_root):
    queue_path = review_root / "ready_to_post.json"
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    data["clips"][1].pop("score")
    queue_path.write_text(json.dumps(data), encoding="utf-8")
    filename = Path(data["clips"][1]["clip_path"]).name
    (review_root / "rankings.json").write_text(
        json.dumps(
            {
                "_sample": "SAMPLE",
                "rankings": [{"filename": filename, "score": 64}],
            }
        ),
        encoding="utf-8",
    )
    board = checkup.gather_review()
    second = next(clip for clip in board["clips"] if clip["id"] == "b22ce002")
    assert second["score"] == 64


def test_api_clips_and_real_thumbnail(board):
    status, raw = _request(board, "GET", "/api/clips")
    assert status == 200
    payload = _json_body(raw)
    assert payload["ok"] is True
    assert payload["counts"]["actionable"] == 3
    assert payload["footer"].startswith("Keep never posts")
    assert "BOLT_REVIEW_TOKEN" not in raw.decode("utf-8")
    status, page = _request(board, "GET", "/")
    assert status == 200
    html = page.decode("utf-8")
    assert board.review_token in html
    assert "window.BOLT_REVIEW_LIVE=true" in html
    status, thumb = _request(board, "GET", "/thumb/a11ce001")
    assert status == 200
    assert thumb[:2] == b"\xff\xd8"
    status, icon = _request(board, "GET", "/assets/menu_bar_icon.png")
    assert status == 200
    assert icon[:8] == b"\x89PNG\r\n\x1a\n"


def test_toss_undo_and_keep(board, review_root):
    port = board.server_address[1]
    origin = f"http://127.0.0.1:{port}"
    token = board.review_token
    before_keep = json.loads(json.dumps(_clip(review_root, "b22ce002")))

    status, raw = _request(
        board,
        "POST",
        "/api/toss",
        token=token,
        origin=origin,
        body={"id": "a11ce001", "reason": "weak hook"},
    )
    assert status == 200, raw
    tossed = _json_body(raw)["clip"]
    assert tossed["status"] == "held"
    assert tossed["hold_reason"] == "weak hook"
    stored = _clip(review_root, "a11ce001")
    assert stored["status"] == "held"
    assert stored["hold_reason"] == "weak hook"
    assert stored["auto_post"]["status"] == "rejected"
    lines = (review_root / "post_rejections.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    logged = json.loads(lines[0])
    assert logged["clip_id"] == "a11ce001"
    assert logged["reason"] == "weak hook"

    status, raw = _request(
        board,
        "POST",
        "/api/undo",
        token=token,
        origin=origin,
        body={"id": "a11ce001"},
    )
    assert status == 200, raw
    restored = _clip(review_root, "a11ce001")
    assert restored["status"] == "ready"
    assert len((review_root / "post_rejections.jsonl").read_text(encoding="utf-8").splitlines()) == 1

    model_path = review_root / "decision_model.json"
    before_scalar = json.loads(model_path.read_text(encoding="utf-8"))["feedback_by_action"]["queue_clip"]
    status, raw = _request(
        board,
        "POST",
        "/api/keep",
        token=token,
        origin=origin,
        body={"id": "b22ce002", "note": "SAMPLE keep"},
    )
    assert status == 200, raw
    kept = _json_body(raw)["clip"]
    assert kept["status"] == "ready"
    assert kept["kept"] is True
    after = _clip(review_root, "b22ce002")
    assert after["status"] == "ready"
    assert after["auto_post"] == before_keep["auto_post"]
    assert after == before_keep
    feedback = (review_root / "unified_memory.jsonl").read_text(encoding="utf-8")
    assert "keep b22ce002" in feedback
    assert "SAMPLE keep" in feedback
    # Toss records -1 and keep records +1 on the same scalar. The keep text
    # lives beside the toss in the decision history; the scalar moves by +1.
    after_scalar = json.loads(model_path.read_text(encoding="utf-8"))["feedback_by_action"]["queue_clip"]
    assert after_scalar == before_scalar + 1


def test_keep_does_not_change_a_ghost_and_missing_token_is_refused(board, review_root):
    original = (review_root / "ready_to_post.json").read_bytes()
    port = board.server_address[1]
    origin = f"http://127.0.0.1:{port}"
    status, raw = _request(
        board,
        "POST",
        "/api/keep",
        token=board.review_token,
        origin=origin,
        body={"id": "c33ce003", "note": ""},
    )
    assert status == 400
    assert _json_body(raw)["ok"] is False
    assert _clip(review_root, "c33ce003")["status"] == "ready"
    assert (review_root / "ready_to_post.json").read_bytes() == original

    status, raw = _request(
        board,
        "POST",
        "/api/keep",
        origin=origin,
        body={"id": "b22ce002", "note": "no token"},
    )
    assert status == 403
    status, raw = _request(
        board,
        "POST",
        "/api/toss",
        token="not-the-token",
        origin=origin,
        body={"id": "b22ce002", "reason": "weak hook"},
    )
    assert status == 403
    assert (review_root / "ready_to_post.json").read_bytes() == original
    assert not (review_root / "post_rejections.jsonl").exists()


def test_toss_requires_a_reason(board, review_root):
    port = board.server_address[1]
    status, raw = _request(
        board,
        "POST",
        "/api/toss",
        token=board.review_token,
        origin=f"http://127.0.0.1:{port}",
        body={"id": "a11ce001", "reason": "   "},
    )
    assert status == 400
    assert _clip(review_root, "a11ce001")["status"] == "ready"


def test_bad_host_and_origin_are_refused(board, review_root):
    original = (review_root / "ready_to_post.json").read_bytes()
    status, raw = _request(board, "GET", "/api/clips", host="evil.example")
    assert status == 403
    status, raw = _request(
        board,
        "POST",
        "/api/toss",
        token=board.review_token,
        origin="http://evil.example",
        body={"id": "a11ce001", "reason": "weak hook"},
    )
    assert status == 403
    assert (review_root / "ready_to_post.json").read_bytes() == original


def test_path_traversal_is_refused(board, review_root):
    secret = review_root.parent / "secret.jpg"
    secret.write_bytes(b"\xff\xd8SECRET-OUTSIDE")
    data = _queue(review_root)
    data["clips"].append(
        {
            "id": "outsid01",
            "title": "SAMPLE outside",
            "score": 10,
            "status": "ready",
            "clip_path": str(secret),
        }
    )
    (review_root / "ready_to_post.json").write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
    link = review_root / "media" / "clips" / "SAMPLE2889961274_clip02_chat_spike_240.jpg"
    link.unlink()
    link.symlink_to(secret)

    for path in (
        "/thumb/../../../../etc/passwd",
        "/thumb/..%2F..%2Fetc%2Fpasswd",
        "/assets/../../Core/config.json",
        "/assets/..%2F..%2FCore%2Fconfig.json",
        "/thumb/outsid01",
        "/thumb/b22ce002",
    ):
        status, raw = _request(board, "GET", path)
        assert status in (403, 404), path
        assert b"SECRET-OUTSIDE" not in raw
        assert b"root:" not in raw

    outside = checkup.thumbnail_for_clip(str(secret), review_root)
    assert outside is None
    escaped = checkup.resolve_clip_in_root(
        str(review_root / "media" / "clips" / ".." / ".." / ".." / "secret.jpg"),
        review_root,
    )
    assert escaped is None
