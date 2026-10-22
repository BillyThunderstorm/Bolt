#!/usr/bin/env python3
"""
Bolt_Mac_App.py — local macOS Bolt.app (menu bar) — READY 21 Oct 2026; not notarized
===============================================================
Honest status for a drag-to-Applications ``dist/Bolt.app`` wrapper.

This is **not** a notarized Mac App Store build and **not** iOS.
Day-to-day use remains ``bolt menubar`` (rumps). Soft-fail prefix:
``Mac app unavailable:``.

  bolt mac-app                      # status (default)
  bolt mac-app status [--json] [--probe]
  bolt mac-app list [--json]
  bolt mac-app build [--dry-run] [--json]   # thin assemble into dist/Bolt.app
  bolt mac-app install [--dry-run]          # build + copy to ~/Applications/Bolt.app
  bolt mac-app open                         # start the menu bar app (once)

Aliases: macapp, mac_app, bolt-app, app-bundle, app-status.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_APP_PY = _REPO / "App" / "app.py"
_BUILD_SH = _REPO / "scripts" / "build_mac_app.sh"
_SETUP_PY = _REPO / "scripts" / "setup.py"
_ICON_CANDIDATES = (
    _REPO / "App" / "assets" / "AppIcon.icns",
    _REPO / "assets" / "AppIcon.icns",
)
_MENU_ICON_CANDIDATES = (
    _REPO / "App" / "assets" / "menu_bar_icon.png",
    _REPO / "assets" / "menu_bar_icon.png",
    _REPO / "App" / "bolt_icon.png",
)
_DIST_APP = _REPO / "dist" / "Bolt.app"
_INSTALLED_APP = Path.home() / "Applications" / "Bolt.app"
_APP_LOG = _REPO / "logs" / "menubar.log"
_VENV_PY = _REPO / ".venv" / "bin" / "python3"
_BUNDLE_ID = "com.thunderstormbilly.bolt"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith("Mac app unavailable:"):
        return msg
    return f"Mac app unavailable: {msg}"


def _first_existing(paths: Tuple[Path, ...]) -> Optional[Path]:
    for p in paths:
        if p.is_file():
            return p
    return None


def _rumps_ok() -> Tuple[bool, str]:
    try:
        import rumps  # noqa: F401

        return True, getattr(rumps, "__version__", "present")
    except Exception as exc:
        return False, str(exc)


def _py2app_ok() -> Tuple[bool, str]:
    try:
        import py2app  # noqa: F401

        ver = getattr(sys.modules.get("py2app"), "__version__", "present")
        return True, str(ver)
    except Exception as exc:
        return False, str(exc)


def _launcher_path(app: Optional[Path] = None) -> Path:
    app = _DIST_APP if app is None else app
    return app / "Contents" / "MacOS" / "Bolt"


def _plist_path(app: Optional[Path] = None) -> Path:
    app = _DIST_APP if app is None else app
    return app / "Contents" / "Info.plist"


def _bundle_looks_valid(app: Optional[Path] = None) -> bool:
    app = _DIST_APP if app is None else app
    return (
        app.is_dir()
        and _launcher_path(app).is_file()
        and os.access(_launcher_path(app), os.X_OK)
        and _plist_path(app).is_file()
    )


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness snapshot for local .app assemble (never claims notarized)."""
    is_darwin = platform.system() == "Darwin"
    rumps_ok, rumps_detail = _rumps_ok()
    py2app_ok, py2app_detail = _py2app_ok()
    icon = _first_existing(_ICON_CANDIDATES)
    menu_icon = _first_existing(_MENU_ICON_CANDIDATES)
    app_exists = _DIST_APP.is_dir()
    launcher = _launcher_path()
    plist = _plist_path()
    valid = _bundle_looks_valid()

    missing: List[str] = []
    if not is_darwin:
        missing.append("not macOS (Darwin)")
    if not _APP_PY.is_file():
        missing.append("missing App/app.py")
    if not _BUILD_SH.is_file():
        missing.append("missing scripts/build_mac_app.sh")
    if not rumps_ok:
        missing.append("rumps not installed (uv sync --extra menubar)")
    if not icon:
        missing.append("missing AppIcon.icns")

    # ready = thin local wrapper can be used (assembled). Still PARTIAL product.
    ready = bool(is_darwin and valid and _APP_PY.is_file())
    hint = None
    if not ready:
        if missing:
            hint = _soft("; ".join(missing[:3]))
        elif not valid:
            hint = _soft("dist/Bolt.app not assembled — try: bolt mac-app build")
        else:
            hint = _soft("not ready")

    out: Dict[str, Any] = {
        "checked_at": _utc_now(),
        "ready": ready,
        "partial": False,
        "is_shipping": False,
        "notarized": False,
        "is_ios": False,
        "prefer": "bolt menubar",
        "platform": platform.system(),
        "platform_is_darwin": is_darwin,
        "app_py": str(_APP_PY) if _APP_PY.is_file() else None,
        "build_script": str(_BUILD_SH) if _BUILD_SH.is_file() else None,
        "setup_py2app": str(_SETUP_PY) if _SETUP_PY.is_file() else None,
        "icon_icns": str(icon) if icon else None,
        "menu_icon": str(menu_icon) if menu_icon else None,
        "dist_app": str(_DIST_APP),
        "dist_app_exists": app_exists,
        "launcher_exists": launcher.is_file(),
        "info_plist_exists": plist.is_file(),
        "bundle_valid": valid,
        "rumps_ok": rumps_ok,
        "rumps_detail": rumps_detail if rumps_ok else _soft(f"rumps ({rumps_detail})"),
        "py2app_ok": py2app_ok,
        "py2app_detail": py2app_detail,
        "bundle_id": _BUNDLE_ID,
        "missing": missing,
        "hint": hint,
        "soft_fail_prefix": "Mac app unavailable:",
    }

    out["dist_stale"] = bool(valid and _bundle_stale(_DIST_APP))
    out["installed_app"] = str(_INSTALLED_APP)
    out["installed"] = _bundle_looks_valid(_INSTALLED_APP)
    out["installed_stale"] = bool(out["installed"] and _bundle_stale(_INSTALLED_APP))
    out["running"] = _menubar_running() if is_darwin else False
    out["log"] = str(_APP_LOG)
    if ready and out["dist_stale"]:
        out["hint"] = "dist/Bolt.app is out of date — run: bolt mac-app install"
    elif ready and out["installed_stale"]:
        out["hint"] = "~/Applications/Bolt.app is out of date — run: bolt mac-app install"
    elif ready and not out["installed"]:
        out["hint"] = "not in ~/Applications yet — run: bolt mac-app install (then find Bolt in Spotlight / Launchpad)"

    if probe and is_darwin and valid:
        ok, problems = _probe(_DIST_APP)
        out["probe_ok"] = ok
        out["probe_problems"] = problems
        if not ok:
            out["ready"] = False
            out["hint"] = _soft(problems[0])
    elif probe and not is_darwin:
        out["probe_ok"] = False
        out["probe_error"] = _soft("not macOS")

    return out


def list_pieces(*, as_json: bool = False) -> int:
    info = status()
    rows = [
        ("platform_darwin", info["platform_is_darwin"]),
        ("App/app.py (menubar)", bool(info["app_py"])),
        ("scripts/build_mac_app.sh", bool(info["build_script"])),
        ("scripts/setup.py (py2app)", bool(info["setup_py2app"])),
        ("AppIcon.icns", bool(info["icon_icns"])),
        ("rumps", bool(info["rumps_ok"])),
        ("py2app (optional full bundle)", bool(info["py2app_ok"])),
        ("dist/Bolt.app", bool(info["dist_app_exists"])),
        ("Contents/MacOS/Bolt", bool(info["launcher_exists"])),
        ("Contents/Info.plist", bool(info["info_plist_exists"])),
        ("bundle_valid", bool(info["bundle_valid"])),
        ("notarized (never claimed)", False),
        ("iOS (never claimed)", False),
    ]
    if as_json:
        print(json.dumps({"pieces": [{"name": n, "ok": ok} for n, ok in rows]}, indent=2))
        return 0
    print("Mac .app pieces (PARTIAL — not notarized / not iOS)")
    for name, ok in rows:
        mark = "OK" if ok else "--"
        print(f"  [{mark}] {name}")
    if info.get("hint"):
        print(f"  → {info['hint']}")
    return 0


def _info_plist_xml() -> str:
    icon = _first_existing(_ICON_CANDIDATES)
    icon_name = icon.name if icon else "AppIcon.icns"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>Bolt</string>
  <key>CFBundleExecutable</key>
  <string>Bolt</string>
  <key>CFBundleIconFile</key>
  <string>{icon_name}</string>
  <key>CFBundleIdentifier</key>
  <string>{_BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Bolt</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>LSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <true/>
  <key>LSHumanReadableCopyright</key>
  <string>Local Bolt wrapper — not notarized</string>
</dict>
</plist>
"""


def _launcher_script() -> str:
    # Thin wrapper: always launch menubar from this checkout (not a frozen copy).
    # Finder starts apps with a bare PATH and no terminal, so add Homebrew,
    # write everything to logs/menubar.log, and never start a second icon.
    repo = str(_REPO)
    app_py = str(_APP_PY)
    venv_py = str(_VENV_PY)
    log = str(_APP_LOG)
    return f"""#!/bin/bash
# Bolt.app launcher — thin checkout wrapper (not notarized). Built by: bolt mac-app build
REPO={repo!r}
LOG={log!r}
APP_PY={app_py!r}
cd "$REPO" || exit 1
mkdir -p "$REPO/logs"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin${{PATH:+:$PATH}}"
export PYTHONPATH="$REPO/Core${{PYTHONPATH:+:$PYTHONPATH}}"
export PYTHONUNBUFFERED=1
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -c 262144 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
echo "===== Bolt.app start $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
if pgrep -f "$APP_PY" >/dev/null 2>&1; then
  echo "already running — not starting a second menu bar icon" >> "$LOG"
  exit 0
fi
PY={venv_py!r}
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi
if [ -z "$PY" ]; then
  echo "Mac app unavailable: no python3 for menubar (run: uv sync --extra menubar)" >> "$LOG"
  osascript -e 'display alert "Bolt cannot start" message "No Python found. In Terminal run: cd ~/developer/Bolt && uv sync --extra menubar"' >/dev/null 2>&1 || true
  exit 1
fi
if ! "$PY" -c "import rumps" >> "$LOG" 2>&1; then
  echo "Mac app unavailable: rumps missing (run: uv sync --extra menubar)" >> "$LOG"
  osascript -e 'display alert "Bolt cannot start" message "The menu bar package is missing. In Terminal run: cd ~/developer/Bolt && uv sync --extra menubar"' >/dev/null 2>&1 || true
  exit 1
fi
exec "$PY" "$APP_PY" >> "$LOG" 2>&1
"""


def _bundle_stale(app: Path) -> bool:
    """True when the bundle's launcher/plist differ from what build would write now."""
    try:
        return (
            _launcher_path(app).read_text(encoding="utf-8") != _launcher_script()
            or _plist_path(app).read_text(encoding="utf-8") != _info_plist_xml()
        )
    except OSError:
        return True


def _menubar_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", str(_APP_PY)], capture_output=True, text=True, timeout=3)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _probe(app: Path) -> Tuple[bool, List[str]]:
    """Check the bundle would really start: launcher syntax, venv rumps, app.py compiles."""
    problems: List[str] = []
    launcher = _launcher_path(app)
    try:
        r = subprocess.run(["bash", "-n", str(launcher)], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            problems.append(f"launcher script has a syntax error ({r.stderr.strip()[:120]}) — fix: bolt mac-app build")
    except Exception as exc:
        problems.append(f"could not check launcher ({exc})")
    py = str(_VENV_PY) if _VENV_PY.exists() else sys.executable
    try:
        r = subprocess.run([py, "-c", "import rumps"], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            problems.append("rumps not importable in .venv — fix: uv sync --extra menubar")
    except Exception as exc:
        problems.append(f"could not import rumps ({exc})")
    try:
        r = subprocess.run([py, "-m", "py_compile", str(_APP_PY)], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            problems.append(f"App/app.py does not compile ({r.stderr.strip()[-160:]})")
    except Exception as exc:
        problems.append(f"could not compile App/app.py ({exc})")
    return (not problems), problems


def try_build(*, dry_run: bool = False, as_json: bool = False) -> int:
    """Assemble a thin dist/Bolt.app that launches bolt menubar from this repo."""
    is_darwin = platform.system() == "Darwin"
    if not is_darwin:
        msg = _soft("not macOS — assemble skipped (status still works)")
        if as_json:
            print(json.dumps({"ok": False, "error": msg, "dry_run": dry_run}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    if not _APP_PY.is_file():
        msg = _soft(f"missing {_APP_PY}")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    rumps_ok, rumps_detail = _rumps_ok()
    if not rumps_ok:
        # Still allow scaffold so status can show bundle_valid after install.
        warn = _soft(f"rumps missing ({rumps_detail}); bundle will launch-fail until uv sync --extra menubar")
    else:
        warn = None

    macos_dir = _DIST_APP / "Contents" / "MacOS"
    resources = _DIST_APP / "Contents" / "Resources"
    launcher = _launcher_path()
    plist = _plist_path()
    icon = _first_existing(_ICON_CANDIDATES)
    menu_icon = _first_existing(_MENU_ICON_CANDIDATES)

    steps = [
        f"mkdir {macos_dir}",
        f"mkdir {resources}",
        f"write {plist}",
        f"write {launcher}",
    ]
    if icon:
        steps.append(f"copy icon → {resources / icon.name}")
    if menu_icon:
        steps.append(f"copy menu icon → {resources / menu_icon.name}")

    if dry_run:
        payload = {
            "ok": True,
            "dry_run": True,
            "would": steps,
            "dist_app": str(_DIST_APP),
            "warn": warn,
            "note": "thin checkout wrapper; not notarized; prefer bolt menubar",
        }
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print("Mac app dry-run: would assemble thin dist/Bolt.app")
            for s in steps:
                print(f"  - {s}")
            if warn:
                print(f"  ⚠ {warn}")
            print("  note: not notarized / not iOS / prefer bolt menubar")
        return 0

    try:
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources.mkdir(parents=True, exist_ok=True)
        plist.write_text(_info_plist_xml(), encoding="utf-8")
        launcher.write_text(_launcher_script(), encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if icon:
            shutil.copy2(icon, resources / icon.name)
        if menu_icon:
            shutil.copy2(menu_icon, resources / menu_icon.name)
    except OSError as exc:
        msg = _soft(f"assemble failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    info = status()
    payload = {
        "ok": True,
        "dist_app": str(_DIST_APP),
        "launcher": str(launcher),
        "bundle_valid": bool(info.get("bundle_valid")),
        "ready": bool(info.get("ready")),
        "notarized": False,
        "is_ios": False,
        "prefer": "bolt menubar",
        "warn": warn,
        "hint": info.get("hint"),
        "open_hint": f"open '{_DIST_APP}'",
    }
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"Assembled {_DIST_APP}")
        print(f"  launcher: {launcher}")
        print("  notarized: false · iOS: false · prefer: bolt menubar")
        if warn:
            print(f"  ⚠ {warn}")
        if info.get("ready"):
            print(f"  status: ready=true (still PARTIAL — not a shipping/.app Store build)")
            print(f"  open: open '{_DIST_APP}'")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
    return 0


def try_install(*, dry_run: bool = False, as_json: bool = False) -> int:
    """Build dist/Bolt.app, then copy it to ~/Applications/Bolt.app (easy to find)."""
    dest = _INSTALLED_APP
    if dest.exists() and not _bundle_looks_valid(dest):
        msg = _soft(f"{dest} exists but isn't a Bolt wrapper — left alone; move it aside first")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
        return 1
    if dest.exists():
        try:
            ident = _plist_path(dest).read_text(encoding="utf-8")
        except OSError:
            ident = ""
        if _BUNDLE_ID not in ident:
            msg = _soft(f"{dest} is a different app (not {_BUNDLE_ID}) — left alone")
            print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
            return 1
    if dry_run:
        msg = {"ok": True, "dry_run": True, "would": [f"build {_DIST_APP}", f"copy → {dest}"]}
        if as_json:
            print(json.dumps(msg, indent=2))
        else:
            print(f"Mac app install dry-run: would build {_DIST_APP} and copy it to {dest}")
        return 0
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        try_build()
    if not _bundle_looks_valid(_DIST_APP):
        msg = _soft("build did not produce a valid dist/Bolt.app — run: bolt mac-app build")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
        return 1
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name("Bolt.app.installing")
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(_DIST_APP, tmp, symlinks=True)
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    except OSError as exc:
        msg = _soft(f"copy to {dest} failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
        return 1
    # Let Spotlight / Launchpad notice it straight away (best effort).
    lsreg = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    if Path(lsreg).exists():
        try:
            subprocess.run([lsreg, "-f", str(dest)], capture_output=True, timeout=10)
        except Exception:
            pass
    if as_json:
        print(json.dumps({"ok": True, "installed": str(dest)}, indent=2))
    else:
        print(f"Installed {dest}")
        print("  Open it from Spotlight (type Bolt) or Finder → Applications. It lives in the menu bar (no Dock icon).")
        print(f"  Log: {_APP_LOG}")
    return 0


def try_open(*, as_json: bool = False) -> int:
    """Start the menu bar app via the installed (or dist) bundle; never a second copy."""
    if _menubar_running():
        msg = "Bolt menu bar app is already running (look for the Bolt icon in the menu bar)."
        print(json.dumps({"ok": True, "already_running": True}) if as_json else msg)
        return 0
    app = _INSTALLED_APP if _bundle_looks_valid(_INSTALLED_APP) else _DIST_APP
    if not _bundle_looks_valid(app):
        msg = _soft("no Bolt.app built yet — run: bolt mac-app install")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
        return 1
    try:
        subprocess.run(["open", str(app)], capture_output=True, timeout=10, check=True)
    except Exception as exc:
        msg = _soft(f"open failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg, file=None if as_json else sys.stderr)
        return 1
    print(json.dumps({"ok": True, "opened": str(app)}) if as_json else f"Opened {app} — Bolt icon should appear in the menu bar.")
    return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("Bolt Mac app (menu bar) — READY, local only, not notarized")
    print(f"  ready: {info.get('ready')}")
    print(f"  platform: {info.get('platform')} (darwin={info.get('platform_is_darwin')})")
    print(f"  rumps: {info.get('rumps_ok')} · py2app: {info.get('py2app_ok')}")
    print(f"  dist: {info.get('dist_app')} (exists={info.get('dist_app_exists')}, valid={info.get('bundle_valid')})")
    print(f"  notarized: false · iOS: false · prefer: {info.get('prefer')}")
    if info.get("icon_icns"):
        print(f"  icon: {info['icon_icns']}")
    print(f"  installed: {info.get('installed_app')} ({'yes' if info.get('installed') else 'no'}"
          f"{', out of date' if info.get('installed_stale') else ''})")
    print(f"  running now: {'yes' if info.get('running') else 'no'} · log: {info.get('log')}")
    if probe:
        print(f"  probe: {'ok — would start' if info.get('probe_ok') else 'problems'}")
        for prob in info.get("probe_problems") or []:
            print(f"    - {prob}")
    if info.get("hint"):
        print(f"  → {info['hint']}")
    elif not info.get("ready"):
        print("  → Mac app unavailable: not assembled — try: bolt mac-app build")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt mac-app — local macOS Bolt.app (menu bar)

  bolt mac-app                       # readiness (default)
  bolt mac-app status [--json] [--probe]
  bolt mac-app list [--json]
  bolt mac-app build [--dry-run] [--json]
  bolt mac-app install [--dry-run]   # build + copy to ~/Applications/Bolt.app
  bolt mac-app open                  # start the menu bar app (never twice)

Soft-fail: "Mac app unavailable:".
Not notarized, not iOS. Prefer: bolt menubar.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "pieces"):
        return list_pieces(as_json=json_out)
    if cmd in ("build", "assemble", "make", "bundle"):
        return try_build(dry_run=dry_run, as_json=json_out)
    if cmd in ("install",):
        return try_install(dry_run=dry_run, as_json=json_out)
    if cmd in ("open", "start", "run"):
        return try_open(as_json=json_out)

    print(f"unknown mac-app action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt mac-app status|list|build|install|open [--json] [--dry-run] [--probe]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
