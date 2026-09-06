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
import subprocess
import sys
import webbrowser
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

APP_ICON = APP_ROOT / "assets" / "menu_bar_icon.png"
APP_ICNS = APP_ROOT / "assets" / "AppIcon.icns"

LAUNCH_SCRIPT = APP_ROOT / "Core" / "launch.py"
DASHBOARD_FILE = APP_ROOT / "App" / "Bolt_Checkup.html"
LOG_DIR = APP_ROOT / "logs"
CONFIG_FILE = APP_ROOT / "Core" / "config.json"
ENV_FILE = APP_ROOT / ".env"
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
    env["PATH"] = env.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"
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
            quit_button="Quit",
        )
        self.process: subprocess.Popen | None = None

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
        ]

    def _title(self, status: str):
        self.title = f"Bolt ({status})"
        self.status_item.title = f"Status: {status}"

    def launch_bolt(self, _):
        if self.process and self.process.poll() is None:
            rumps.alert("Bolt is already running")
            return
        if not LAUNCH_SCRIPT.exists():
            rumps.alert(f"Launch script not found:\n{LAUNCH_SCRIPT}")
            return

        self._title("starting...")
        try:
            # --no-checklist: menu-bar launch must not block on the voice checklist
            self.process = subprocess.Popen(
                _bolt_cmd(["launch", "--no-checklist"]),
                cwd=str(APP_ROOT),
                env=_run_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._title("running")
            rumps.notification("Bolt", "Launched", "Bolt is now running in the background")
        except Exception as exc:
            self._title("launch failed")
            rumps.alert(f"Failed to launch Bolt: {exc}")

    def process_recording(self, _):
        self._title("processing...")
        try:
            result = subprocess.run(
                _bolt_cmd(["recordings", "latest"]),
                cwd=str(APP_ROOT),
                env=_run_env(),
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self._title("ready")
            rumps.notification("Bolt", "Processing complete", "Latest recording processed")
            if result.stdout.strip():
                print(result.stdout[-500:])
        except subprocess.CalledProcessError as exc:
            self._title("process error")
            err = (exc.stderr or exc.stdout or str(exc))[:500]
            rumps.alert(f"Processing failed:\n{err}")
        except Exception as exc:
            self._title("process error")
            rumps.alert(f"Processing failed: {exc}")

    def open_dashboard(self, _):
        # Refresh Bolt_data.js when Checkup_Writer is available, then open HTML
        try:
            subprocess.run(
                _bolt_cmd(["checkup"]),
                cwd=str(APP_ROOT),
                env=_run_env(),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass
        if DASHBOARD_FILE.exists():
            webbrowser.open(DASHBOARD_FILE.resolve().as_uri())
        else:
            rumps.alert(
                "Dashboard HTML not found.\n"
                f"Expected: {DASHBOARD_FILE}\n"
                "Run: bolt checkup"
            )

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
            self._title("stopped")
            rumps.notification("Bolt", "Stopped", "Bolt process terminated")
        else:
            rumps.alert("Bolt is not running")


def main():
    if not LAUNCH_SCRIPT.exists():
        print(f"bolt menubar: Core/launch.py not found under {APP_ROOT}", file=sys.stderr)
        raise SystemExit(1)
    BoltApp().run()


if __name__ == "__main__":
    main()
