#!/usr/bin/env python3
"""
app.py — Bolt macOS Menu Bar App
=================================
Lightweight native-ish wrapper using rumps. Provides:
- Menu bar icon showing Bolt status
- Launch / Stop Bolt (runs launch.py)
- Process latest recording
- Open dashboard (Bolt_Checkup.html)
- Quick config / logs access

Build with:
  python3 setup.py py2app

Result:
  dist/Bolt.app
"""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

import rumps

# Project root is two levels up from this file when bundled under Contents/Resources
APP_ROOT = Path(__file__).resolve().parent.parent.parent
if not (APP_ROOT / "launch.py").exists():
    # Fallback: running from source tree
    APP_ROOT = Path(__file__).resolve().parent.parent

APP_ICON = APP_ROOT / "assets" / "menu_bar_icon.png"
APP_ICNS = APP_ROOT / "assets" / "AppIcon.icns"

LAUNCH_SCRIPT = APP_ROOT / "launch.py"
PROCESS_SCRIPT = APP_ROOT / "launch.py"
DASHBOARD_FILE = APP_ROOT / "docs" / "Bolt_Checkup.html"
LOG_DIR = APP_ROOT / "logs"
CONFIG_FILE = APP_ROOT / "config.json"
ENV_FILE = APP_ROOT / ".env"


def _python_cmd():
    """Return the command to run Python inside the project venv."""
    venv_python = APP_ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return [str(venv_python)]
    return [sys.executable]


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

        self._title("starting...")
        try:
            env = os.environ.copy()
            env["PATH"] = env.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"
            self.process = subprocess.Popen(
                _python_cmd() + [str(LAUNCH_SCRIPT)],
                cwd=str(APP_ROOT),
                env=env,
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
            env = os.environ.copy()
            env["PATH"] = env.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"
            subprocess.run(
                _python_cmd() + [str(PROCESS_SCRIPT), "process"],
                cwd=str(APP_ROOT),
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self._title("ready")
            rumps.notification("Bolt", "Processing complete", "Latest recording processed")
        except subprocess.CalledProcessError as exc:
            self._title("process error")
            rumps.alert(f"Processing failed:\n{exc.stderr[:500]}")
        except Exception as exc:
            self._title("process error")
            rumps.alert(f"Processing failed: {exc}")

    def open_dashboard(self, _):
        if DASHBOARD_FILE.exists():
            webbrowser.open(f"file://{DASHBOARD_FILE}")
        else:
            rumps.alert("Dashboard HTML not found. Run Checkup_Writer first.")

    def open_logs(self, _):
        if LOG_DIR.exists():
            subprocess.run(["open", str(LOG_DIR)])
        else:
            rumps.alert("Logs folder not found.")

    def open_config(self, _):
        paths = []
        if CONFIG_FILE.exists():
            paths.append(str(CONFIG_FILE))
        if ENV_FILE.exists():
            paths.append(str(ENV_FILE))
        if paths:
            subprocess.run(["open", "-t"] + paths)
        else:
            rumps.alert("No config files found.")

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
    BoltApp().run()


if __name__ == "__main__":
    main()
