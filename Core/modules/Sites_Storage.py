#!/usr/bin/env python3
"""
Sites_Storage.py — local site-data write + storage cron readiness
=================================================================
Soft-fail surface for:
  - Local ``bolt site`` → ``Data/site-data.json`` (always useful)
  - Optional ``--push`` to GitHub (soft-fail; never hang status)
  - Storage monitor / rotate / optimize scripts + crontab (advisory)

Does not install crontab, push, or deploy Cloudflare Pages.

Soft-fail prefixes:
  - ``Sites unavailable: …`` — site write / git push
  - ``Storage cron unavailable: …`` — missing storage scripts

READY for a stranger = local site write + storage scripts present.
Cron and git remote are advisory hints (William often has them).
Cloudflare Pages deploy is PARTIAL via bolt pages (William-specific; not stranger-ready).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
_CORE = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"
_DATA = _REPO / "Data"
_SITE_DATA = _DATA / "site-data.json"
_ALERTS_ENV = _DATA / "configs" / "storage_alerts.env"

_SCRIPT_NAMES = (
    "storage_monitor.sh",
    "media_rotation.sh",
    "storage_optimization.sh",
    "site_data_writer.py",
)

_CRON_MARKERS = (
    "storage_monitor",
    "media_rotation",
    "storage_optimization",
    "site_data_writer",
)


def _ensure_scripts_path() -> None:
    s = str(_SCRIPTS)
    if s not in sys.path:
        sys.path.insert(0, s)


def _git_remote_configured() -> bool:
    """True if cwd is a git repo with at least one remote. Never pushes."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0 or (r.stdout or "").strip() != "true":
            return False
        r2 = subprocess.run(
            ["git", "remote"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool((r2.stdout or "").strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _crontab_lines() -> List[str]:
    """Best-effort matching crontab lines. Soft-fail → []."""
    try:
        r = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return []
        out: List[str] = []
        for line in (r.stdout or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(m in line for m in _CRON_MARKERS):
                out.append(line.rstrip())
        return out
    except (OSError, subprocess.TimeoutExpired):
        return []


def _script_presence() -> Dict[str, bool]:
    return {name: (_SCRIPTS / name).exists() for name in _SCRIPT_NAMES}


def _site_mtime() -> Optional[str]:
    try:
        if _SITE_DATA.exists():
            ts = _SITE_DATA.stat().st_mtime
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Sites + storage cron readiness. Never raises; never hangs on network."""
    try:
        scripts = _script_presence()
        site_writer_ok = bool(scripts.get("site_data_writer.py"))
        storage_scripts_ok = all(
            scripts.get(n)
            for n in (
                "storage_monitor.sh",
                "media_rotation.sh",
                "storage_optimization.sh",
            )
        )
        # Local write path is usable when writer exists and Data/ is creatable.
        data_ok = True
        try:
            _DATA.mkdir(parents=True, exist_ok=True)
        except OSError:
            data_ok = False
        site_ready = site_writer_ok and data_ok
        storage_ready = storage_scripts_ok
        cron_jobs = _crontab_lines()
        cron_installed = bool(cron_jobs)
        git_push_ready = _git_remote_configured()
        alerts_env = _ALERTS_ENV.exists()
        ready = site_ready and storage_ready

        hints: List[str] = []
        if not site_ready:
            if not site_writer_ok:
                hints.append(
                    "Sites unavailable: scripts/site_data_writer.py missing"
                )
            elif not data_ok:
                hints.append(f"Sites unavailable: cannot write under {_DATA}")
        if not storage_ready:
            missing = [
                n
                for n in (
                    "storage_monitor.sh",
                    "media_rotation.sh",
                    "storage_optimization.sh",
                )
                if not scripts.get(n)
            ]
            hints.append(
                "Storage cron unavailable: missing scripts/ "
                + ", ".join(missing)
            )
        if site_ready and not git_push_ready:
            hints.append(
                "Sites unavailable: git remote not configured "
                "(local write still works; --push soft-fails)"
            )
        if storage_ready and not cron_installed:
            hints.append(
                "Storage cron unavailable: no matching crontab lines "
                "(scripts present — install cron manually if desired; "
                "bolt storage monitor|rotate|optimize still work)"
            )

        if ready and git_push_ready and cron_installed:
            hint = (
                "Local site write + storage scripts + cron OK. "
                "Try: bolt site / bolt sites status / bolt storage status"
            )
        elif ready and not hints:
            hint = (
                "Local site write + storage scripts ready. "
                "Try: bolt site / bolt storage status"
            )
        elif hints:
            hint = " | ".join(hints)
        else:
            hint = "Try: bolt sites status --json"

        info: Dict[str, Any] = {
            "ready": ready,
            "site_ready": site_ready,
            "storage_ready": storage_ready,
            "cron_installed": cron_installed,
            "scripts": scripts,
            "site_data_path": str(_SITE_DATA),
            "site_data_mtime": _site_mtime(),
            "alerts_env": alerts_env,
            "git_push_ready": git_push_ready,
            "cron_jobs": cron_jobs,
            "hint": hint,
        }

        if probe:
            info["probe_ok"] = False
            info["probe_detail"] = ""
            if not site_writer_ok:
                info["probe_detail"] = (
                    "Sites unavailable: scripts/site_data_writer.py missing"
                )
                info["hint"] = info["probe_detail"]
            else:
                try:
                    _ensure_scripts_path()
                    from site_data_writer import write_site_data  # type: ignore

                    probe_path = _DATA / ".site-data-probe.json"
                    write_site_data(push=False, output_path=str(probe_path))
                    ok = probe_path.exists() and probe_path.stat().st_size > 0
                    try:
                        probe_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    if ok:
                        info["probe_ok"] = True
                        info["probe_detail"] = (
                            f"ok — local write via site_data_writer "
                            f"(under {_DATA.name}/)"
                        )
                    else:
                        info["probe_detail"] = (
                            "Sites unavailable: probe write produced empty file"
                        )
                        info["hint"] = info["probe_detail"]
                except Exception as exc:
                    info["probe_detail"] = (
                        f"Sites unavailable: probe write failed ({exc})"
                    )
                    info["hint"] = info["probe_detail"]
        return info
    except Exception as exc:
        return {
            "ready": False,
            "site_ready": False,
            "storage_ready": False,
            "cron_installed": False,
            "scripts": {},
            "site_data_path": str(_SITE_DATA),
            "site_data_mtime": None,
            "alerts_env": False,
            "git_push_ready": False,
            "cron_jobs": [],
            "hint": f"Sites unavailable: status failed ({exc})",
            "error": str(exc),
        }


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    """Print readiness (or JSON). Always exit 0 — soft-fail informational."""
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("\n  Sites / storage cron readiness")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pok = info.get("probe_ok")
        pflag = "✓" if pok else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    sflag = "✓" if info.get("site_ready") else "○"
    print(f"  {sflag}  site local write: {bool(info.get('site_ready'))}")
    print(f"      path: {info.get('site_data_path')}")
    if info.get("site_data_mtime"):
        print(f"      mtime: {info.get('site_data_mtime')}")
    print(f"      git_push_ready: {bool(info.get('git_push_ready'))}")
    print(f"      alerts_env: {bool(info.get('alerts_env'))}")
    tflag = "✓" if info.get("storage_ready") else "○"
    print(f"  {tflag}  storage scripts: {bool(info.get('storage_ready'))}")
    scripts = info.get("scripts") or {}
    for name, present in scripts.items():
        print(f"      {'✓' if present else '○'}  scripts/{name}")
    cflag = "✓" if info.get("cron_installed") else "○"
    print(f"  {cflag}  cron_installed: {bool(info.get('cron_installed'))}")
    jobs = info.get("cron_jobs") or []
    if jobs:
        for line in jobs:
            print(f"      • {line}")
    else:
        print("      (no matching crontab lines — advisory only)")
    print()
    print("  Try:")
    print("    bolt site                     # local Data/site-data.json write")
    print("    bolt sites status --json      # machine-readable readiness")
    print("    bolt sites status --probe     # dry local write probe")
    print("    bolt storage status           # sizes + this summary")
    print("  Note: Cloudflare Pages deploy is PARTIAL via bolt pages (not stranger-ready).")
    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt sites — local site-data + storage cron readiness

  bolt sites                 # readiness (default)
  bolt sites status [--json] [--probe]
  bolt site                  # write Data/site-data.json (no push)
  bolt site --push           # write + soft-fail git push
  bolt storage status        # media sizes + cron/scripts summary

Local write always works via REPO_ROOT. Optional --push / crontab are
advisory. Soft-fail: "Sites unavailable:" / "Storage cron unavailable:".
Cloudflare Pages deploy: see bolt pages (PARTIAL; William-specific).
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)
    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready", "sites", "storage-cron"):
        return print_status(as_json=json_out, probe=probe)
    print(f"unknown sites action: {cmd}", file=sys.stderr)
    print("  try: bolt sites status [--json] [--probe]", file=sys.stderr)
    return 0  # soft-fail informational — never crash callers


if __name__ == "__main__":
    raise SystemExit(main())
