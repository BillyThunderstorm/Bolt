#!/usr/bin/env python3
"""Stream Deck helper: start the overlay server if needed, then change counts.

Usage:
  overlay_action.py kills 1
  overlay_action.py wins -1
  overlay_action.py reset
  overlay_action.py ensure
  overlay_action.py open
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python3"
SERVER = ROOT / "scripts" / "overlay_server.py"
LOG = ROOT / "logs" / "overlay_server.log"
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"


def _get(path: str, timeout: float = 1.5) -> bytes:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as res:
        return res.read()


def healthy() -> bool:
    try:
        _get("/api/health", timeout=0.4)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_server() -> None:
    if healthy():
        return
    if not PY.is_file():
        raise SystemExit(f"Bolt venv python missing: {PY}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [str(PY), str(SERVER), "--port", str(PORT)],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(25):
        time.sleep(0.12)
        if healthy():
            return
    raise SystemExit(
        f"overlay server did not start on {BASE} — see {LOG}"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = (args[0] if args else "ensure").lower()

    if cmd == "open":
        ensure_server()
        subprocess.run(
            ["open", f"{BASE}/thunder-diamond-counter.html?edit=1"],
            check=False,
        )
        return 0

    ensure_server()
    if cmd == "ensure":
        return 0
    if cmd == "reset":
        _get("/api/reset?type=all")
        return 0
    if cmd in ("kills", "wins", "kill", "win"):
        kind = "kills" if cmd.startswith("kill") else "wins"
        delta = args[1] if len(args) > 1 else "1"
        _get(f"/api/change?type={kind}&delta={delta}")
        return 0
    print("usage: overlay_action.py kills|wins|reset|ensure|open [delta]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
