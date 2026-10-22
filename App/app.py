#!/usr/bin/env python3
"""
app.py — Bolt macOS Menu Bar App
=================================
Lightweight native-ish wrapper using rumps. Provides:
- Menu bar icon showing Bolt status
- Launch / Stop Bolt (Core/launch.py live --no-checklist)
- Process latest recording (bolt recordings / launch.py process)
- Open dashboard (App/Bolt_Checkup.html, refreshed via Checkup_Writer)
- Quick config / logs access

Run:
  bolt menubar
  # or: uv sync --extra menubar && .venv/bin/python App/app.py

Build with:
  python3 setup.py py2app

Result:
  dist/Bolt.app
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Find the Bolt repo root whether running from source or a py2app bundle."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent,                 # App/app.py → repo root
        here.parent.parent.parent,          # py2app Resources nesting
        Path.cwd(),
    ]
    for root in candidates:
        if (root / "Core" / "launch.py").exists() and (root / "bin" / "bolt").exists():
            return root
    # Last resort: walk parents
    for parent in here.parents:
        if (parent / "Core" / "launch.py").exists() and (parent / "bin" / "bolt").exists():
            return parent
    return here.parent.parent


APP_ROOT = _resolve_repo_root()

try:
    import rumps
except ImportError:
    print(
        "bolt menubar needs rumps (macOS only).\n"
        "  cd "
        f"{APP_ROOT}\n"
        "  uv sync --extra menubar\n"
        "  bolt menubar",
        file=sys.stderr,
    )
    raise SystemExit(1)

def _first(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


# Icons live in App/assets (older checkouts used a top-level assets/ folder).
APP_ICON = _first(
    APP_ROOT / "App" / "assets" / "menu_bar_icon.png",
    APP_ROOT / "assets" / "menu_bar_icon.png",
)
APP_ICNS = _first(
    APP_ROOT / "App" / "assets" / "AppIcon.icns",
    APP_ROOT / "assets" / "AppIcon.icns",
)

LAUNCH_SCRIPT = APP_ROOT / "Core" / "launch.py"
DASHBOARD_FILE = APP_ROOT / "App" / "Bolt_Checkup.html"
LOG_DIR = APP_ROOT / "logs"
LAUNCH_LOG = LOG_DIR / "menubar_bolt.log"
CONFIG_FILE = APP_ROOT / "Core" / "config.json"
# Bolt reads .env.local before .env, so open the one that actually wins.
ENV_FILE = _first(APP_ROOT / ".env.local", APP_ROOT / ".env")
BOLT_SHIM = APP_ROOT / ".venv" / "bin" / "bolt"
VENV_PYTHON = APP_ROOT / ".venv" / "bin" / "python3"


def _python_cmd() -> list[str]:
    """Return the command to run Python inside the project venv."""
    if VENV_PYTHON.exists():
        return [str(VENV_PYTHON)]
    return [sys.executable]


def _bolt_cmd(args: list[str]) -> list[str]:
    """Prefer the uv-managed bolt shim; fall back to Core/launch.py for launch/process."""
    if BOLT_SHIM.exists():
        return [str(BOLT_SHIM)] + args
    if args and args[0] == "launch":
        return _python_cmd() + [str(LAUNCH_SCRIPT), "live"] + args[1:]
    if args and args[0] == "recordings":
        return _python_cmd() + [str(LAUNCH_SCRIPT), "process"] + args[1:]
    if args and args[0] == "checkup":
        env_py = _python_cmd()
        return env_py + ["-m", "modules.Checkup_Writer"] + args[1:]
    return _python_cmd() + [str(LAUNCH_SCRIPT)] + args


def _run_env() -> dict:
    env = os.environ.copy()
    parts = [p for p in env.get("PATH", "").split(":") if p]
    for extra in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        if extra not in parts:
            parts.append(extra)
    env["PATH"] = ":".join(parts)
    core = str(APP_ROOT / "Core")
    env["PYTHONPATH"] = core + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    return env


class BoltApp(rumps.App):
    def __init__(self):
        icon_path = str(APP_ICON) if APP_ICON.exists() else None
        super().__init__(
            "Bolt",
            icon=icon_path,
            template=True,
            quit_button=None,
        )
        self.process: subprocess.Popen | None = None
        self._busy: set[str] = set()
        # Background jobs post (title, message, is_error) here; the main-thread
        # timer shows them, so the menu never freezes while Bolt works.
        self._events: "queue.Queue[tuple[str, str, bool]]" = queue.Queue()

        self.status_item = rumps.MenuItem("Status: idle", callback=None)

        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem("Launch Bolt", callback=self.launch_bolt),
            rumps.MenuItem("Process Recording", callback=self.process_recording),
            None,
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            rumps.MenuItem("Open Logs Folder", callback=self.open_logs),
            rumps.MenuItem("Open Config", callback=self.open_config),
            None,
            rumps.MenuItem("Stop Bolt", callback=self.stop_bolt),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self._timer = rumps.Timer(self._tick, 2)
        self._timer.start()

    def _title(self, status: str):
        self.status_item.title = f"Status: {status}"

    # ---- main-thread housekeeping -------------------------------------
    def _tick(self, _):
        while True:
            try:
                title, message, is_error = self._events.get_nowait()
            except queue.Empty:
                break
            if is_error:
                rumps.alert(title, message)
            else:
                rumps.notification("Bolt", title, message)
        if self.process is not None:
            code = self.process.poll()
            if code is not None:
                self.process = None
                if code == 0:
                    self._title("stopped")
                    rumps.notification("Bolt", "Stopped", "Bolt finished.")
                else:
                    self._title(f"stopped (error {code})")
                    rumps.notification(
                        "Bolt", "Bolt stopped with an error",
                        f"See logs/{LAUNCH_LOG.name} (Open Logs Folder).",
                    )
            elif "processing" not in self._busy:
                self._title("running")
        elif self._busy:
            self._title("processing..." if "processing" in self._busy else "working...")
        elif self.status_item.title in ("Status: processing...", "Status: working..."):
            self._title("ready")

    def _in_background(self, key: str, func):
        if key in self._busy:
            rumps.notification("Bolt", "Already working", "That job is still running.")
            return

        def runner():
            try:
                func()
            except Exception as exc:  # never let a job kill the menu bar
                self._events.put(("Something went wrong", str(exc)[:500], True))
            finally:
                self._busy.discard(key)

        self._busy.add(key)
        threading.Thread(target=runner, daemon=True).start()

    # ---- menu actions ---------------------------------------------------
    def launch_bolt(self, _):
        if self.process and self.process.poll() is None:
            rumps.alert("Bolt is already running")
            return
        if not LAUNCH_SCRIPT.exists():
            rumps.alert(f"Launch script not found:\n{LAUNCH_SCRIPT}")
            return

        self._title("starting...")
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log = open(LAUNCH_LOG, "a", encoding="utf-8")
            log.write(f"\n===== Bolt launched from the menu bar {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            log.flush()
            # --no-checklist: menu-bar launch must not block on the voice checklist
            self.process = subprocess.Popen(
                _bolt_cmd(["launch", "--no-checklist"]),
                cwd=str(APP_ROOT),
                env=_run_env(),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            log.close()
            self._title("running")
            rumps.notification("Bolt", "Launched", "Bolt is now running in the background")
        except Exception as exc:
            self._title("launch failed")
            rumps.alert(f"Failed to launch Bolt: {exc}")

    def process_recording(self, _):
        def job():
            try:
                result = subprocess.run(
                    _bolt_cmd(["recordings", "latest"]),
                    cwd=str(APP_ROOT),
                    env=_run_env(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
            except subprocess.TimeoutExpired:
                self._events.put(("Processing took too long", "Stopped after 30 minutes. Try: bolt recordings latest", True))
                return
            _append_log("Process Recording", result.stdout, result.stderr, result.returncode)
            if result.returncode == 0:
                self._events.put(("Processing complete", "Latest recording processed", False))
            else:
                err = (result.stderr or result.stdout or f"exit {result.returncode}").strip()[-500:]
                self._events.put(("Processing failed", err, True))

        self._title("processing...")
        rumps.notification("Bolt", "Processing", "Working on your latest recording…")
        self._in_background("processing", job)

    def open_dashboard(self, _):
        def job():
            # Refresh Bolt_data.js when Checkup_Writer is available, then open HTML
            try:
                subprocess.run(
                    _bolt_cmd(["checkup"]),
                    cwd=str(APP_ROOT),
                    env=_run_env(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass
            if DASHBOARD_FILE.exists():
                subprocess.run(["open", str(DASHBOARD_FILE)])
            else:
                self._events.put((
                    "Dashboard not found",
                    f"Expected: {DASHBOARD_FILE}\nRun: bolt checkup",
                    True,
                ))

        self._in_background("dashboard", job)

    def open_logs(self, _):
        if LOG_DIR.exists():
            subprocess.run(["open", str(LOG_DIR)])
        else:
            rumps.alert(f"Logs folder not found:\n{LOG_DIR}")

    def open_config(self, _):
        paths = []
        if CONFIG_FILE.exists():
            paths.append(str(CONFIG_FILE))
        if ENV_FILE.exists():
            paths.append(str(ENV_FILE))
        if paths:
            subprocess.run(["open", "-t"] + paths)
        else:
            rumps.alert(
                "No config files found.\n"
                f"Expected: {CONFIG_FILE} and/or {ENV_FILE}"
            )

    def stop_bolt(self, _):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self._title("stopped")
            rumps.notification("Bolt", "Stopped", "Bolt process terminated")
        else:
            rumps.alert("Bolt is not running")

    def quit_app(self, _):
        # Don't leave a launched Bolt running headless after the icon is gone.
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        rumps.quit_application()


def _append_log(label: str, out: str, err: str, code: int) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {label} {time.strftime('%Y-%m-%d %H:%M:%S')} (exit {code}) =====\n")
            fh.write((out or "")[-4000:])
            fh.write((err or "")[-4000:])
    except OSError:
        pass


def main():
    if not LAUNCH_SCRIPT.exists():
        print(f"bolt menubar: Core/launch.py not found under {APP_ROOT}", file=sys.stderr)
        raise SystemExit(1)
    BoltApp().run()


if __name__ == "__main__":
    main()
