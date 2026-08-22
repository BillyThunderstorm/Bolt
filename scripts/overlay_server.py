#!/usr/bin/env python3
"""Local overlay server for OBS + Stream Deck.

Serves App/overlay over http://127.0.0.1:8766 and keeps kill/win counts
so Stream Deck buttons (curl) and OBS browser sources stay in sync.

  bolt overlay                 # start (leave running while you stream)
  bolt overlay --port 8766

OBS Browser Sources (not file:// — Stream Deck cannot reach file://):
  Counter:  http://127.0.0.1:8766/thunder-diamond-counter.html
  Cam:      http://127.0.0.1:8766/thunder-diamond-cam.html
  Wide cam: http://127.0.0.1:8766/thunder-diamond-cam.html?shape=wide

Stream Deck (System → Open a script in scripts/streamdeck/):
  overlay_kill.sh / overlay_win.sh / overlay_reset.sh
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR  # noqa: E402

OVERLAY_DIR = REPO_ROOT / "App" / "overlay"
STATE_FILE = DATA_DIR / "overlay_counter.json"
DEFAULT_PORT = 8766

_lock = threading.Lock()
_state = {"kills": 0, "wins": 0}


def _load_state() -> None:
    global _state
    if not STATE_FILE.is_file():
        return
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        _state = {
            "kills": max(0, int(payload.get("kills") or 0)),
            "wins": max(0, int(payload.get("wins") or 0)),
        }
    except (OSError, ValueError, TypeError):
        pass


def _save_state() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def _snapshot() -> dict[str, int]:
    return {"kills": _state["kills"], "wins": _state["wins"]}


def _change(kind: str, delta: int) -> dict[str, Any]:
    kind = (kind or "").lower().strip()
    if kind not in ("kills", "wins"):
        raise ValueError("type must be kills or wins")
    with _lock:
        before = _state[kind]
        _state[kind] = max(0, before + int(delta))
        actual = _state[kind] - before
        counts = _snapshot()
        _save_state()
    return {"ok": True, "counts": counts, "delta": {kind: actual}}


def _reset(kind: str) -> dict[str, Any]:
    kind = (kind or "all").lower().strip()
    with _lock:
        delta: dict[str, int] = {}
        if kind in ("all", "kills"):
            delta["kills"] = -_state["kills"]
            _state["kills"] = 0
        if kind in ("all", "wins"):
            delta["wins"] = -_state["wins"]
            _state["wins"] = 0
        counts = _snapshot()
        _save_state()
    return {"ok": True, "counts": counts, "delta": delta}


class OverlayHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OVERLAY_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[overlay] " + (format % args) + "\n")

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        if path in ("/api/state", "/api/counts"):
            self._json({"ok": True, "counts": _snapshot(), "delta": {}})
            return
        if path == "/api/health":
            self._json({"ok": True, "port": self.server.server_address[1]})
            return
        if path == "/api/change":
            kind = (qs.get("type") or qs.get("kind") or ["kills"])[0]
            try:
                delta = int((qs.get("delta") or ["1"])[0])
                self._json(_change(kind, delta))
            except (ValueError, TypeError) as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/reset":
            kind = (qs.get("type") or qs.get("kind") or ["all"])[0]
            self._json(_reset(kind))
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bolt OBS overlay server (Stream Deck + browser sources).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    if not OVERLAY_DIR.is_dir():
        print(f"overlay folder missing: {OVERLAY_DIR}", file=sys.stderr)
        return 1

    _load_state()
    server = ThreadingHTTPServer((args.host, args.port), OverlayHandler)
    base = f"http://{args.host}:{args.port}"
    print("Bolt overlay server")
    print("─" * 48)
    print(f"  Counter  {base}/thunder-diamond-counter.html")
    print(f"  Cam      {base}/thunder-diamond-cam.html")
    print(f"  Wide cam {base}/thunder-diamond-cam.html?shape=wide")
    print()
    print("OBS: Browser Source → those URLs (not Local File).")
    print("     Width/height 560×300 (counter) or match your webcam (cam).")
    print("     Custom CSS: body { background-color: rgba(0,0,0,0) !important; }")
    print()
    print("Stream Deck: System → Open the apps in App/overlay/streamdeck/")
    print("             (Overlay Kill.app / Overlay Win.app / Overlay Reset.app)")
    print("             Do not Open the .sh files — macOS opens those as text.")
    print("Leave this running while you stream. Ctrl+C to stop.")
    print("─" * 48)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\noverlay server stopped.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
