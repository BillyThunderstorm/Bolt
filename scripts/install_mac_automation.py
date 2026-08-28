#!/usr/bin/env python3
"""
install_mac_automation.py — launchd, 5pm briefing cron, Apple Shortcuts
=======================================================================
  python3 scripts/install_mac_automation.py           # all
  python3 scripts/install_mac_automation.py launchd
  python3 scripts/install_mac_automation.py cron
  python3 scripts/install_mac_automation.py shortcuts
  python3 scripts/install_mac_automation.py reminders-test
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
VENV_PY = REPO / ".venv" / "bin" / "python3"
BOLT = REPO / ".venv" / "bin" / "bolt"
OCR = SCRIPT_DIR / "ocr_to_editable.py"
TERM = SCRIPT_DIR / "mac_run_in_terminal.sh"
SHORTCUT_DIR = SCRIPT_DIR / "macos_shortcuts"
SIGNED_DIR = SHORTCUT_DIR / "signed"

BRIEFING_CRON_MARK = "Daily at 5pm: evening briefing"
PROCESS_CRON_MARK = "Every 2 hours: auto-process any new recordings"
OLD_BRIEFING_MARKERS = (
    "Daily at 7am: morning briefing",
    "daily_briefing.py --send",
)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def install_launchd() -> int:
    print("── launchd ──")
    cmd = [str(VENV_PY if VENV_PY.exists() else sys.executable), str(SCRIPT_DIR / "autostart.py"), "install"]
    result = subprocess.run(cmd)
    return result.returncode


def _read_crontab() -> str:
    r = _run(["crontab", "-l"])
    if r.returncode != 0:
        return ""
    return r.stdout or ""


def _write_crontab(text: str) -> None:
    subprocess.run(["crontab", "-"], input=text, text=True, check=True)


def install_cron() -> int:
    print("── cron ──")
    existing = _read_crontab()
    lines = existing.splitlines()
    kept: list[str] = []
    skip_next_blank = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Drop the old disabled 7am briefing block and the stale process line
        if "DISABLED 2026-08-09" in line or "morning briefing via SMS" in line:
            i += 1
            continue
        if BRIEFING_CRON_MARK in line:
            i += 1
            if i < len(lines) and "daily_briefing.py" in lines[i]:
                i += 1
            continue
        if PROCESS_CRON_MARK in line:
            i += 1
            if i < len(lines) and "launch.py process" in lines[i]:
                i += 1
            continue
        if "daily_briefing.py --send" in line:
            i += 1
            continue
        if line.strip().endswith("launch.py process >> /Users/carter/developer/Bolt/logs/auto_process.log 2>&1"):
            i += 1
            continue
        kept.append(line)
        i += 1

    briefing = (
        f"# {BRIEFING_CRON_MARK} → Apple Reminders + Mac banner + email\n"
        f"0 17 * * * cd {REPO} && {VENV_PY} {SCRIPT_DIR / 'daily_briefing.py'} --send "
        f">> {REPO / 'logs' / 'daily_briefing.log'} 2>&1"
    )
    process = (
        f"# {PROCESS_CRON_MARK}\n"
        f"0 */2 * * * cd {REPO} && {VENV_PY} {REPO / 'Core' / 'launch.py'} process --no-checklist "
        f">> {REPO / 'logs' / 'auto_process.log'} 2>&1"
    )

    body = "\n".join(kept).rstrip() + "\n\n" + briefing + "\n\n" + process + "\n"
    _write_crontab(body)
    print("Installed 17:00 briefing + fixed recordings process job.")
    print(_read_crontab())
    return 0


def _action(identifier: str, params: dict) -> dict:
    params = dict(params)
    params.setdefault("UUID", str(uuid.uuid4()).upper())
    return {
        "WFWorkflowActionIdentifier": identifier,
        "WFWorkflowActionParameters": params,
    }


def _workflow(actions: list[dict], *, input_classes: list[str], name: str) -> dict:
    return {
        "WFWorkflowClientRelease": "3.0",
        "WFWorkflowClientVersion": "900",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,
            "WFWorkflowIconStartColor": 431817727,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["WatchKit", "NCWidget"],
        "WFWorkflowInputContentItemClasses": input_classes,
        "WFWorkflowActions": actions,
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowName": name,
    }


def _shell_shortcut(name: str, script: str, *, input_classes=None) -> dict:
    return _workflow(
        [
            _action(
                "is.workflow.actions.runshellscript",
                {
                    "InputMode": "as arguments",
                    "Script": script,
                    "Shell": "/bin/zsh",
                },
            ),
        ],
        input_classes=input_classes or ["WFStringContentItem"],
        name=name,
    )


def _ocr_shortcut(name: str = "Extract Text from Photos") -> dict:
    py = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    script = f'''
set -euo pipefail
FILES=("$@")
if [[ ${{#FILES[@]}} -eq 0 ]]; then
  echo "No images received" >&2
  exit 2
fi
"{py}" "{OCR}" --open "${{FILES[@]}}"
'''
    select = _action(
        "is.workflow.actions.selectphoto",
        {"WFSelectMultiplePhotos": True},
    )
    run = _action(
        "is.workflow.actions.runshellscript",
        {
            "InputMode": "as arguments",
            "Script": script.strip() + "\n",
            "Shell": "/bin/zsh",
        },
    )
    return _workflow(
        [select, run],
        input_classes=[
            "WFImageContentItem",
            "WFPhotoMediaContentItem",
            "WFGenericFileContentItem",
        ],
        name=name,
    )


def _wrapup_shortcut() -> dict:
    ask = _action(
        "is.workflow.actions.ask",
        {
            "WFAskActionPrompt": "What shipped today? (Cancel to only show the week card.)",
            "WFInputType": "Text",
        },
    )
    script = f'''
set -euo pipefail
cd "{REPO}"
BOLT="{BOLT}"
if [[ ! -x "$BOLT" ]]; then
  BOLT="{sys.executable} {REPO / 'bin' / 'bolt'}"
fi
SHIPPED="$*"
if [[ -n "${{SHIPPED// /}}" ]]; then
  $BOLT week done "$SHIPPED"
else
  $BOLT week
fi
'''
    run = _action(
        "is.workflow.actions.runshellscript",
        {
            "InputMode": "as arguments",
            "Script": script.strip() + "\n",
            "Shell": "/bin/zsh",
        },
    )
    return _workflow(
        [ask, run],
        input_classes=["WFStringContentItem"],
        name="Bolt Wrap-Up",
    )


def shortcut_specs() -> dict[str, dict]:
    term = str(TERM)
    return {
        "Bolt Morning": _shell_shortcut(
            "Bolt Morning",
            f'"{term}" day\n',
        ),
        "Bolt Review Queue": _shell_shortcut(
            "Bolt Review Queue",
            f'"{term}" day --decide\n',
        ),
        "Bolt Stats": _shell_shortcut(
            "Bolt Stats",
            (
                f'cd "{REPO}"\n'
                + (
                    f'"{BOLT}" stats sync\n'
                    if BOLT.exists()
                    else f'"{sys.executable}" "{REPO / "bin" / "bolt"}" stats sync\n'
                )
            ),
        ),
        "Bolt Wrap-Up": _wrapup_shortcut(),
        "Extract Text from Photos": _ocr_shortcut("Extract Text from Photos"),
        "Extract Text from JPGs to PDF": _ocr_shortcut("Extract Text from JPGs to PDF"),
    }


def install_shortcuts() -> int:
    print("── shortcuts ──")
    TERM.chmod(0o755)
    OCR.chmod(0o755)
    SHORTCUT_DIR.mkdir(parents=True, exist_ok=True)
    SIGNED_DIR.mkdir(parents=True, exist_ok=True)
    unsigned_dir = SHORTCUT_DIR / "unsigned"
    unsigned_dir.mkdir(parents=True, exist_ok=True)

    opened = 0
    for name, workflow in shortcut_specs().items():
        # Filenames become the Shortcuts library name, so keep spaces.
        # `shortcuts sign` only accepts .shortcut / .wflow, not .plist
        raw = unsigned_dir / f"{name}.shortcut"
        signed = SIGNED_DIR / f"{name}.shortcut"
        with raw.open("wb") as fh:
            plistlib.dump(workflow, fh)
        signed_result = _run(
            [
                "shortcuts",
                "sign",
                "--mode",
                "anyone",
                "--input",
                str(raw),
                "--output",
                str(signed),
            ]
        )
        if signed_result.returncode != 0:
            print(f"  sign failed: {name}")
            print(signed_result.stderr or signed_result.stdout)
            continue
        print(f"  signed {signed.name}")
        _run(["open", str(signed)])
        opened += 1

    print()
    print(f"Opened {opened} shortcut import dialog(s).")
    print("Click Add on each. For the JPG shortcut: keep 'Extract Text from Photos'")
    print("and delete the old gallery 'Extract Text from JPGs to PDF' if you get a duplicate.")
    print("Siri: open each shortcut → (i) → Add to Siri.")
    return 0 if opened else 1


def reminders_test() -> int:
    print("── reminders test ──")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO / 'Core'}" + (
        f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
    )
    result = subprocess.run(
        [str(VENV_PY if VENV_PY.exists() else sys.executable), "-m", "modules.Apple_Reminders"],
        cwd=str(REPO),
        env=env,
    )
    return result.returncode


def main(argv: list[str]) -> int:
    args = argv or ["all"]
    steps = {
        "launchd": install_launchd,
        "cron": install_cron,
        "shortcuts": install_shortcuts,
        "reminders-test": reminders_test,
    }
    if args == ["all"] or args == ["--all"]:
        order = ["launchd", "cron", "shortcuts"]
    else:
        order = args
    rc = 0
    for name in order:
        fn = steps.get(name)
        if not fn:
            print(f"unknown step: {name}", file=sys.stderr)
            print("use: launchd | cron | shortcuts | reminders-test | all")
            return 2
        rc = fn() or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
