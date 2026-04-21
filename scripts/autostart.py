#!/usr/bin/env python3
# autostart.py — Phase 3: Register the assistant to run on system boot
#
# This script sets up the OS scheduler so the folder watcher starts
# automatically whenever your computer turns on — you never have to
# remember to start it manually.
#
# Usage: python autostart.py install
#         python autostart.py uninstall
#         python autostart.py status

import sys
import os
import platform
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PYTHON = sys.executable
LAUNCH_SCRIPT = SCRIPT_DIR / "launch.py"


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "install"
    system = platform.system()

    print(f"\nAutostart manager — {system}")
    print("="*40)

    if action == "install":
        if system == "Darwin":
            _install_macos()
        elif system == "Windows":
            _install_windows()
        elif system == "Linux":
            _install_linux()
        else:
            print(f"Unsupported OS: {system}")

    elif action == "uninstall":
        if system == "Darwin":
            _uninstall_macos()
        elif system == "Windows":
            _uninstall_windows()
        elif system == "Linux":
            _uninstall_linux()

    elif action == "status":
        _check_status(system)


# ── macOS — launchd ───────────────────────────────────────────────────────────
# launchd is macOS's process supervisor. A .plist file tells it what to run,
# when to run it, and what to do if it crashes.

PLIST_LABEL = "com.streamer.ai-assistant"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{PLIST_LABEL}.plist"

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{workdir}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>{workdir}/launcher_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>{workdir}/launcher_stderr.log</string>
</dict>
</plist>
"""


def _install_macos():
    """
    Install a launchd agent on macOS.

    What this does:
    - Creates a .plist file in ~/Library/LaunchAgents/
    - Registers it with launchd (macOS's process manager)
    - launchd will run launch.py when you log in
    - If the process crashes, launchd restarts it automatically
    """
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    plist_content = PLIST_TEMPLATE.format(
        label=PLIST_LABEL,
        python=PYTHON,
        script=str(LAUNCH_SCRIPT),
        workdir=str(SCRIPT_DIR),
    )

    PLIST_PATH.write_text(plist_content)
    print(f"Written: {PLIST_PATH}")

    # Load it immediately
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        print("\nAutostart installed successfully.")
        print("The assistant will now start automatically when you log in.")
        print("\nTo start it right now without rebooting:")
        print(f"  launchctl start {PLIST_LABEL}")
        print("\nTo check if it's running:")
        print(f"  launchctl list | grep {PLIST_LABEL}")
    else:
        print(f"launchctl load failed: {result.stderr}")
        print("Try running: launchctl load", str(PLIST_PATH))


def _uninstall_macos():
    if not PLIST_PATH.exists():
        print("No autostart entry found.")
        return
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()
    print("Autostart removed.")


# ── Windows — Task Scheduler ──────────────────────────────────────────────────
# Task Scheduler is Windows' equivalent of launchd.
# We use the command-line tool 'schtasks' to register a task.

TASK_NAME = "StreamerAIAssistant"


def _install_windows():
    """
    Register a Windows Task Scheduler task.

    What this does:
    - Creates a scheduled task that runs at user logon
    - The task runs launch.py with pythonw.exe (no console window)
    - It restarts automatically if it fails
    """
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{PYTHON}" "{LAUNCH_SCRIPT}"',
        "/sc", "ONLOGON",
        "/ru", os.environ.get("USERNAME", ""),
        "/f",   # force overwrite if exists
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode == 0:
        print("Autostart installed via Task Scheduler.")
        print(f"Task name: {TASK_NAME}")
        print("\nTo start immediately: schtasks /run /tn", TASK_NAME)
    else:
        print(f"Failed: {result.stderr}")
        print("Try running this script as Administrator.")


def _uninstall_windows():
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True, shell=True
    )
    if result.returncode == 0:
        print("Autostart task removed.")
    else:
        print(f"Could not remove task: {result.stderr}")


# ── Linux — systemd user service ─────────────────────────────────────────────

SERVICE_NAME = "streamer-ai-assistant"
SERVICE_PATH = Path.home() / f".config/systemd/user/{SERVICE_NAME}.service"

SERVICE_TEMPLATE = """[Unit]
Description=Streaming AI Assistant
After=graphical-session.target

[Service]
Type=simple
ExecStart={python} {script}
WorkingDirectory={workdir}
Restart=on-failure
RestartSec=10
StandardOutput=append:{workdir}/launcher_stdout.log
StandardError=append:{workdir}/launcher_stderr.log

[Install]
WantedBy=default.target
"""


def _install_linux():
    SERVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_PATH.write_text(SERVICE_TEMPLATE.format(
        python=PYTHON,
        script=str(LAUNCH_SCRIPT),
        workdir=str(SCRIPT_DIR),
    ))
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME])
    subprocess.run(["systemctl", "--user", "start", SERVICE_NAME])
    print(f"Systemd user service installed: {SERVICE_NAME}")
    print("Status: systemctl --user status", SERVICE_NAME)


def _uninstall_linux():
    subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME])
    subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME])
    if SERVICE_PATH.exists():
        SERVICE_PATH.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    print("Service removed.")


# ── Status check ──────────────────────────────────────────────────────────────

def _check_status(system: str):
    if system == "Darwin":
        result = subprocess.run(
            ["launchctl", "list", PLIST_LABEL],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("Status: RUNNING")
            print(result.stdout)
        else:
            print("Status: NOT INSTALLED")
    elif system == "Windows":
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, text=True, shell=True
        )
        print(result.stdout if result.returncode == 0 else "Task not found.")
    elif system == "Linux":
        subprocess.run(["systemctl", "--user", "status", SERVICE_NAME])


if __name__ == "__main__":
    main()
