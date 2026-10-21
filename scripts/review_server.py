#!/usr/bin/env python3
"""Local clip review board. Keep records taste. Keep never posts.

  bolt review
  bolt review --port 8767 --no-open

Binds 127.0.0.1 only. Toss calls Peak_Hour_Notifier.reject_next_clip.
Undo calls unhold_clip. Keep calls ThinkLearnDecideEngine.learn_from_feedback
and does not change queue status or auto_post.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import CORE_DIR, REPO_ROOT  # noqa: E402

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from modules import Bolt_Memory as bolt_memory  # noqa: E402
from modules import Checkup_Writer as checkup  # noqa: E402
from modules import Peak_Hour_Notifier as peak  # noqa: E402
from modules import Think_Learn_Decide as think  # noqa: E402
from modules.Clip_Ranker import parse_clip_filename  # noqa: E402

APP_DIR = REPO_ROOT / "App"
PAGE_FILE = APP_DIR / "Clip_Review.html"
ASSETS_DIR = APP_DIR / "assets"
DEFAULT_PORT = 8767
LOOPBACK = "127.0.0.1"
MAX_BODY = 16_384
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ASSET_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)
_TOKEN_HEADER = "X-Bolt-Review-Token"
_VIDEO_CHUNK = 64 * 1024
_VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".webm": "video/webm",
}


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    review_token: str = ""


def fixture_bindings(root: Path) -> list[tuple[Any, str, Any]]:
    """Module globals the board reads and writes. Tests monkeypatch these."""
    root = root.resolve()
    return [
        (checkup, "QUEUE_FILE", root / "ready_to_post.json"),
        (checkup, "RANKINGS_FILE", root / "rankings.json"),
        (checkup, "REVIEW_MEDIA_ROOT", root),
        (peak, "READY_FILE", root / "ready_to_post.json"),
        (peak, "REJECTION_LOG", root / "post_rejections.jsonl"),
        (think, "DECISION_MODEL_FILE", root / "decision_model.json"),
        (think, "UNIFIED_MEMORY_FILE", root / "unified_memory.jsonl"),
        (think, "SOURCE_REGISTRY_FILE", root / "source_registry.json"),
        (think, "DATA_DIR", root),
        (think, "LOGS_DIR", root / "logs"),
        (think, "MEMORY_DIR", root / "memory"),
        (bolt_memory, "MEMORY_ROOT", root),
        (bolt_memory, "MEMORY_FILE", root / "MEMORY.md"),
        (bolt_memory, "refresh_memory_index", None),
    ]


def apply_fixture_root(root: Path) -> None:
    """Point queue, rejection, and learning writes at a sample directory.

    Used by `--fixtures` / BOLT_REVIEW_FIXTURES so a screenshot run does not
    touch William's Data files. The live `bolt review` command does not call this.
    """
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    for obj, name, value in fixture_bindings(root):
        setattr(obj, name, value)
    memory = root / "MEMORY.md"
    if not memory.exists():
        memory.write_text("# SAMPLE\n\n## Recent Notes\n", encoding="utf-8")


def _clip_by_id(data: dict, clip_id: str) -> dict | None:
    for clip in data.get("clips") or []:
        if isinstance(clip, dict) and str(clip.get("id") or "") == clip_id:
            return clip
    return None


def _public_clip(clip_id: str) -> dict | None:
    board = checkup.gather_review()
    for clip in board.get("clips") or []:
        if clip.get("id") == clip_id:
            return clip
    return None


def keep_clip(clip_id: str, note: str = "") -> tuple[dict | None, str | None, int]:
    """Record a keep. The queue file, status, and auto_post plan stay as they were."""
    if not _ID_RE.fullmatch(clip_id):
        return None, "Missing clip id.", 400
    before = b""
    if peak.READY_FILE.exists():
        before = peak.READY_FILE.read_bytes()
    data = peak._load_ready()
    clip = _clip_by_id(data, clip_id)
    if clip is None:
        return None, "No clip with that id.", 404
    if not checkup.review_file_exists(str(clip.get("clip_path") or "")):
        return None, "Keep is off for a missing file. Toss can still hold it.", 400
    parsed = parse_clip_filename(str(clip.get("clip_path") or ""))
    trigger = str(clip.get("trigger") or parsed.get("trigger") or "")
    score = clip.get("score")
    if score is None:
        score = ""
    note = " ".join(str(note or "").split())[:240]
    text = f"keep {clip_id} trigger={trigger} score={score} {note}".strip()
    engine = think.ThinkLearnDecideEngine({"memory_auto_refresh": False})
    engine.learn_from_feedback("queue_clip", accepted=True, feedback_text=text)
    after = peak.READY_FILE.read_bytes() if peak.READY_FILE.exists() else b""
    if after != before:
        return None, "Keep refused to change the queue.", 500
    public = _public_clip(clip_id)
    if public is None:
        return None, "No clip with that id.", 404
    public["kept"] = True
    return public, None, 200


def toss_clip(clip_id: str, reason: str) -> tuple[dict | None, str | None, int]:
    """Hold a clip through the existing rejection path. Does not post."""
    if not _ID_RE.fullmatch(clip_id):
        return None, "Missing clip id.", 400
    reason = " ".join(str(reason or "").split())
    if not reason:
        return None, "A reason is required.", 400
    if len(reason) > 500:
        return None, "Reason is too long.", 400
    held = peak.reject_next_clip(reason, clip_id=clip_id)
    if not held:
        return None, "That clip is not ready to hold.", 404
    public = _public_clip(clip_id)
    if public is None:
        return None, "That clip is not ready to hold.", 404
    return public, None, 200


def undo_clip(clip_id: str) -> tuple[dict | None, str | None, int]:
    """Put a held clip back with unhold_clip. Does not approve it."""
    if not _ID_RE.fullmatch(clip_id):
        return None, "Missing clip id.", 400
    restored = peak.unhold_clip(clip_id)
    if not restored:
        return None, "That clip is not held.", 404
    public = _public_clip(clip_id)
    if public is None:
        return None, "That clip is not held.", 404
    return public, None, 200


def _unsafe_path(path: str) -> bool:
    lowered = unquote(path).lower()
    raw = path.lower()
    if ".." in path or ".." in lowered or "\\" in path or "\x00" in path:
        return True
    if "%2e" in raw or "%2f" in raw or "%5c" in raw:
        return True
    return False


def _parse_byte_range(header: str, size: int) -> tuple[int, int] | None:
    """One `bytes=` range. None means the range cannot be satisfied."""
    if size < 0:
        return None
    match = _RANGE_RE.fullmatch(header.strip())
    if match is None:
        return None
    start_text, end_text = match.group(1), match.group(2)
    if start_text == "" and end_text == "":
        return None
    if start_text == "":
        length = int(end_text)
        if length <= 0 or size == 0:
            return None
        if length > size:
            length = size
        return size - length, size - 1
    start = int(start_text)
    if start >= size:
        return None
    if end_text == "":
        end = size - 1
    else:
        end = int(end_text)
        if end >= size:
            end = size - 1
    if end < start:
        return None
    return start, end


def _casefold_child(parent: Path, name: str) -> Path | None:
    """One path segment, case-insensitive. Does not require the target to stay inside a root."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
        return None
    direct = parent / name
    try:
        if direct.exists() or direct.is_symlink():
            return direct
    except OSError:
        return None
    if not parent.is_dir():
        return None
    folded = name.casefold()
    try:
        for child in parent.iterdir():
            if child.name.casefold() == folded:
                return child
    except OSError:
        return None
    return None


def _video_path_denied(raw: str) -> bool:
    """True when a clip path points at a file the board must not stream.

    Missing files are not denied — the caller answers those with 404.
    A file outside REVIEW_MEDIA_ROOT, including a symlink that leaves it,
    and a file whose suffix is not a playable video, are denied.
    """
    base = checkup.REVIEW_MEDIA_ROOT.resolve()
    text = str(raw or "").strip()
    if not text or "\x00" in text:
        return False
    direct = Path(text)
    if direct.is_absolute():
        try:
            if direct.exists() or direct.is_symlink():
                resolved = direct.resolve()
                try:
                    resolved.relative_to(base)
                except ValueError:
                    return resolved.is_file()
        except OSError:
            return False
    posix = text.replace("\\", "/")
    parts = [part for part in PurePosixPath(posix).parts if part not in ("/", "")]
    if any(part in ("", ".", "..") for part in parts):
        return True
    lowers = [part.casefold() for part in parts]
    rel: list[str] | None = None
    for index, name in enumerate(lowers):
        if name == "media":
            rel = parts[index:]
            break
    if rel is None:
        for index, name in enumerate(lowers):
            if name in ("clips", "vertical_clips") and (
                index == 0 or lowers[index - 1] != "media"
            ):
                rel = parts[index:]
                break
    if not rel:
        return False
    current = base
    escaped = False
    for part in rel:
        nxt = _casefold_child(current, part)
        if nxt is None:
            return False
        try:
            resolved = nxt.resolve()
            resolved.relative_to(base)
        except ValueError:
            escaped = True
            current = nxt
            break
        except OSError:
            return False
        current = nxt
    try:
        final = current.resolve()
    except OSError:
        return escaped
    if escaped:
        return final.is_file()
    if final.is_file() and final.suffix.lower() not in _VIDEO_TYPES:
        return True
    return False


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[review] " + (fmt % args) + "\n")

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._bytes(status, body, "application/json; charset=utf-8")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _deny(self, status: int, error: str) -> None:
        self._json({"ok": False, "error": error}, status=status)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if not host or host.startswith("["):
            return False
        hostname = host.split(":", 1)[0]
        return hostname == LOOPBACK

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None or origin == "":
            return True
        port = self.server.server_address[1]
        return origin == f"http://{LOOPBACK}:{port}"

    def _token_ok(self) -> bool:
        sent = self.headers.get(_TOKEN_HEADER) or ""
        expected = self.server.review_token
        if not expected or not sent:
            return False
        return secrets.compare_digest(sent, expected)

    def _guard(self, *, write: bool) -> bool:
        if not self._host_ok():
            self._deny(403, "refused")
            return False
        if write:
            if not self._origin_ok() or not self._token_ok():
                self._deny(403, "refused")
                return False
        return True

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or "0")
        if length < 0 or length > MAX_BODY:
            self._deny(400, "Body is too large.")
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._deny(400, "Body must be JSON.")
            return None
        if not isinstance(payload, dict):
            self._deny(400, "Body must be a JSON object.")
            return None
        return payload

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._deny(403, "refused")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if _unsafe_path(parsed.path) or _unsafe_path(path):
            if not self._host_ok():
                self._deny(403, "refused")
                return
            self._deny(403, "refused")
            return
        if not self._guard(write=False):
            return
        route = path.rstrip("/") or "/"
        if route in ("/", "/index.html", "/clip_review.html"):
            self._serve_page()
            return
        if route == "/api/clips":
            self._json({"ok": True, **checkup.gather_review()})
            return
        if route == "/api/health":
            self._json({"ok": True, "host": LOOPBACK, "port": self.server.server_address[1]})
            return
        if route.startswith("/thumb/"):
            self._serve_thumb(route[len("/thumb/") :])
            return
        if route.startswith("/video/"):
            self._serve_video(route[len("/video/") :])
            return
        if route.startswith("/assets/"):
            self._serve_asset(route[len("/assets/") :])
            return
        self._deny(404, "Not found.")

    def _drain_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return
        if length <= 0:
            return
        self.rfile.read(min(length, MAX_BODY))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"
        if _unsafe_path(parsed.path) or _unsafe_path(path):
            self._drain_body()
            self._deny(403, "refused")
            return
        if not self._guard(write=True):
            self._drain_body()
            return
        payload = self._read_json()
        if payload is None:
            return
        clip_id = str(payload.get("id") or "").strip()
        if path == "/api/keep":
            clip, error, status = keep_clip(clip_id, str(payload.get("note") or ""))
        elif path == "/api/toss":
            clip, error, status = toss_clip(clip_id, str(payload.get("reason") or ""))
        elif path == "/api/undo":
            clip, error, status = undo_clip(clip_id)
        else:
            self._deny(404, "Not found.")
            return
        if error:
            self._json({"ok": False, "error": error}, status=status)
            return
        self._json({"ok": True, "clip": clip})

    def _serve_page(self) -> None:
        if not PAGE_FILE.is_file():
            self._deny(500, "Clip review page is missing.")
            return
        html = PAGE_FILE.read_text(encoding="utf-8")
        boot = (
            "<script>window.BOLT_REVIEW_TOKEN="
            + json.dumps(self.server.review_token)
            + ";window.BOLT_REVIEW_LIVE=true;</script>"
        )
        html = html.replace("<!-- BOLT_REVIEW_BOOT -->", boot, 1)
        self._bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_asset(self, name: str) -> None:
        if not _ASSET_RE.fullmatch(name) or ".." in name:
            self._deny(403, "refused")
            return
        path = (ASSETS_DIR / name).resolve()
        try:
            path.relative_to(ASSETS_DIR.resolve())
        except ValueError:
            self._deny(403, "refused")
            return
        if not path.is_file():
            self._deny(404, "Not found.")
            return
        kind = "application/octet-stream"
        if path.suffix.lower() == ".png":
            kind = "image/png"
        elif path.suffix.lower() in (".jpg", ".jpeg"):
            kind = "image/jpeg"
        self._bytes(200, path.read_bytes(), kind)

    def _serve_thumb(self, clip_id: str) -> None:
        if not _ID_RE.fullmatch(clip_id):
            self._deny(403, "refused")
            return
        thumb = None
        for row in checkup._load_queue():
            if not isinstance(row, dict) or str(row.get("id") or "") != clip_id:
                continue
            thumb = checkup.thumbnail_for_clip(str(row.get("clip_path") or ""))
            break
        if thumb is None or not thumb.is_file():
            self._deny(404, "No thumbnail.")
            return
        try:
            thumb.relative_to(checkup.REVIEW_MEDIA_ROOT.resolve())
        except ValueError:
            self._deny(403, "refused")
            return
        if thumb.suffix.lower() not in (".jpg", ".jpeg"):
            self._deny(403, "refused")
            return
        self._bytes(200, thumb.read_bytes(), "image/jpeg")

    def _serve_video(self, clip_id: str) -> None:
        if not _ID_RE.fullmatch(clip_id):
            self._deny(403, "refused")
            return
        clip_path = ""
        found = False
        for row in checkup._load_queue():
            if not isinstance(row, dict) or str(row.get("id") or "") != clip_id:
                continue
            found = True
            clip_path = str(row.get("clip_path") or "")
            break
        if not found:
            self._deny(404, "No video.")
            return
        video = checkup.resolve_clip_in_root(clip_path)
        if video is None or not video.is_file():
            if _video_path_denied(clip_path):
                self._deny(403, "refused")
                return
            self._deny(404, "No video.")
            return
        try:
            video.relative_to(checkup.REVIEW_MEDIA_ROOT.resolve())
        except ValueError:
            self._deny(403, "refused")
            return
        kind = _VIDEO_TYPES.get(video.suffix.lower())
        if kind is None:
            self._deny(403, "refused")
            return
        self._stream_video(video, kind)

    def _stream_video(self, path: Path, content_type: str) -> None:
        """Send a video, honoring a single Range so Safari can play it.

        Reads the file in chunks. The whole clip is never loaded into memory.
        """
        try:
            size = path.stat().st_size
        except OSError:
            self._deny(404, "No video.")
            return
        range_header = self.headers.get("Range")
        start = 0
        end = size - 1 if size else -1
        status = 200
        if range_header is not None:
            parsed = _parse_byte_range(range_header, size)
            if parsed is None:
                self.send_response(416)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                return
            start, end = parsed
            status = 206
        length = 0 if end < start else end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if length <= 0:
            return
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(_VIDEO_CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except OSError:
            return


def create_server(host: str, port: int, token: str | None = None) -> ReviewHTTPServer:
    if host != LOOPBACK:
        raise ValueError("bolt review only binds 127.0.0.1")
    httpd = ReviewHTTPServer((host, port), ReviewHandler)
    httpd.review_token = token or secrets.token_urlsafe(24)
    return httpd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local clip review board. Keep never posts."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=LOOPBACK)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Print the URL without opening a browser.",
    )
    parser.add_argument(
        "--fixtures",
        default="",
        help="Write queue and learning files under this directory instead of Data/.",
    )
    args = parser.parse_args(argv)

    if args.host != LOOPBACK:
        print("bolt review only binds 127.0.0.1", file=sys.stderr)
        return 2
    if not PAGE_FILE.is_file():
        print(f"clip review page missing: {PAGE_FILE}", file=sys.stderr)
        return 1

    fixture_arg = (args.fixtures or os.environ.get("BOLT_REVIEW_FIXTURES") or "").strip()
    if fixture_arg:
        fixture_root = Path(fixture_arg).expanduser()
        if not fixture_root.is_dir():
            print(f"fixture directory missing: {fixture_root}", file=sys.stderr)
            return 1
        apply_fixture_root(fixture_root)
        print(f"Using fixture data in {fixture_root.resolve()}")

    try:
        server = create_server(args.host, args.port)
    except OSError as exc:
        print(f"Could not bind {LOOPBACK}:{args.port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://{LOOPBACK}:{server.server_address[1]}/"
    print("Bolt clip review")
    print("─" * 48)
    print(f"  Board    {url}")
    print("  Keep records taste and does not approve or post.")
    print("  Toss holds a clip (bolt dontpost). Undo puts it back.")
    print("Leave this running. Ctrl+C to stop.")
    print("─" * 48)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception as exc:
            print(f"Could not open a browser ({exc}). Open {url}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nclip review stopped.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
