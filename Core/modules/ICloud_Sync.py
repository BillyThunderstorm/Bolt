#!/usr/bin/env python3
"""
ICloud_Sync.py — soft-fail CLI for Bolt iCloud / multi-Mac sync helpers (PARTIAL)
================================================================================
Wraps documented scripts from Docs/AI_Guide.md:
  scripts/move_to_icloud.sh       — preferred one-step copy into iCloud Drive
  scripts/migrate_to_shared.sh    — legacy 2-step /Users/Shared hop
  scripts/setup_icloud.sh         — legacy second-account iCloud pickup

Soft-fail prefix: ``iCloud unavailable:``.

CLI (via ``bolt icloud``):
  status [--json] [--probe]
  list [--json]
  run [--dry-run|--apply] [--script move|shared|setup] [--json]

Stay PARTIAL — Darwin / iCloud Drive gated; William multi-Mac glue; not stranger-ready.
Distinct from PARTIAL ``bolt mac-auto`` (launchd/cron/Shortcuts) and READY local checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "iCloud unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_MOVE = _REPO / "scripts" / "move_to_icloud.sh"
_SHARED = _REPO / "scripts" / "migrate_to_shared.sh"
_SETUP = _REPO / "scripts" / "setup_icloud.sh"
_GUIDE = _REPO / "Docs" / "AI_Guide.md"
_SCRIPTS = {
    "move": _MOVE,
    "shared": _SHARED,
    "setup": _SETUP,
}
_DEFAULT_SCRIPT = "move"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _icloud_root() -> Path:
    home = Path.home()
    return home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def _icloud_bolt(root: Optional[Path] = None) -> Path:
    return (root or _icloud_root()) / "Bolt"


def _path_under_icloud(path: Path, icloud: Path) -> bool:
    try:
        path.resolve().relative_to(icloud.resolve())
        return True
    except Exception:
        return False


def _dir_nonempty(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
        return True
    except Exception:
        return False


def status(*, probe: bool = False) -> Dict[str, Any]:
    """iCloud sync readiness. Never raises. PARTIAL / not stranger-ready."""
    try:
        is_darwin = platform.system() == "Darwin"
        icloud = _icloud_root()
        dest = _icloud_bolt(icloud)
        shared = Path("/Users/Shared/Bolt")
        repo_in_icloud = _path_under_icloud(_REPO, icloud) if icloud.is_dir() else False

        engines = {name: path.is_file() for name, path in _SCRIPTS.items()}
        engines_ok = all(engines.values())
        icloud_present = icloud.is_dir()
        dest_present = dest.is_dir()
        dest_nonempty = _dir_nonempty(dest)
        shared_present = shared.is_dir()

        missing: List[str] = []
        if not is_darwin:
            missing.append("not macOS (Darwin)")
        if is_darwin and not icloud_present:
            missing.append(
                "iCloud Drive folder missing "
                "(System Settings → Apple ID → iCloud → iCloud Drive ON)"
            )
        for name, ok in engines.items():
            if not ok:
                missing.append(f"missing {_SCRIPTS[name].relative_to(_REPO)}")

        # ready = darwin + iCloud folder + preferred move script (pieces exist)
        ready = bool(is_darwin and icloud_present and engines.get("move"))

        if ready:
            if repo_in_icloud:
                hint = (
                    "checkout already under iCloud Drive · "
                    "bolt icloud list / run --dry-run"
                )
            elif dest_nonempty:
                hint = (
                    "iCloud Drive/Bolt copy present · "
                    "bolt icloud run --dry-run (preferred: move script)"
                )
            else:
                hint = (
                    "darwin + iCloud Drive + move script ready · "
                    "bolt icloud run --dry-run  (use --apply to copy; skips recordings/)"
                )
            error = ""
        else:
            error = _soft("; ".join(missing[:3]) if missing else "not ready")
            hint = error

        out: Dict[str, Any] = {
            "checked_at": _iso(),
            "ready": ready,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt icloud",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "darwin": is_darwin,
            "platform": platform.system(),
            "repo": str(_REPO),
            "repo_under_icloud": repo_in_icloud,
            "icloud_root": str(icloud),
            "icloud_present": icloud_present,
            "icloud_bolt": str(dest),
            "icloud_bolt_present": dest_present,
            "icloud_bolt_nonempty": dest_nonempty,
            "shared_bolt": str(shared),
            "shared_bolt_present": shared_present,
            "engines": {k: str(v) for k, v in _SCRIPTS.items()},
            "engines_present": engines,
            "engines_ok": engines_ok,
            "preferred_script": "move",
            "docs_guide": str(_GUIDE),
            "docs_guide_present": _GUIDE.is_file(),
            "missing": missing,
            "error": error,
            "hint": hint,
            "probe": bool(probe),
            "probe_ok": None,
            "probe_detail": "",
        }

        if probe:
            details: List[str] = []
            if not is_darwin:
                details.append("not Darwin")
                out["probe_ok"] = False
            elif not icloud_present:
                details.append("iCloud Drive missing")
                out["probe_ok"] = False
            else:
                details.append("iCloud Drive ok")
                details.append(
                    "repo under iCloud" if repo_in_icloud else "repo outside iCloud"
                )
                details.append(
                    "Bolt copy nonempty" if dest_nonempty else "no Bolt copy yet"
                )
                if shared_present:
                    details.append("/Users/Shared/Bolt present (legacy hop)")
                out["probe_ok"] = bool(ready)
            out["probe_detail"] = "; ".join(details)
            if not out["probe_ok"] and not out.get("error"):
                out["error"] = _soft(out["probe_detail"])
                out["hint"] = out["error"]
        return out
    except Exception as exc:
        return {
            "checked_at": _iso(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt icloud",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "darwin": platform.system() == "Darwin",
            "platform": platform.system(),
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "probe": bool(probe),
            "probe_ok": False,
        }


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {
            "id": "platform_darwin",
            "ok": bool(st.get("darwin")),
            "detail": st.get("platform") or "",
        },
        {
            "id": "icloud_drive",
            "ok": bool(st.get("icloud_present")),
            "detail": st.get("icloud_root") or "",
        },
        {
            "id": "move_to_icloud.sh",
            "ok": bool((st.get("engines_present") or {}).get("move")),
            "detail": (st.get("engines") or {}).get("move", ""),
        },
        {
            "id": "migrate_to_shared.sh (legacy)",
            "ok": bool((st.get("engines_present") or {}).get("shared")),
            "detail": (st.get("engines") or {}).get("shared", ""),
        },
        {
            "id": "setup_icloud.sh (legacy)",
            "ok": bool((st.get("engines_present") or {}).get("setup")),
            "detail": (st.get("engines") or {}).get("setup", ""),
        },
        {
            "id": "icloud_bolt_copy",
            "ok": bool(st.get("icloud_bolt_nonempty")),
            "detail": (
                f"{st.get('icloud_bolt')} nonempty={st.get('icloud_bolt_nonempty')}"
            ),
        },
        {
            "id": "repo_under_icloud",
            "ok": bool(st.get("repo_under_icloud")),
            "detail": st.get("repo") or "",
        },
        {
            "id": "shared_bolt_legacy",
            "ok": bool(st.get("shared_bolt_present")),
            "detail": st.get("shared_bolt") or "",
        },
        {
            "id": "docs_ai_guide",
            "ok": bool(st.get("docs_guide_present")),
            "detail": st.get("docs_guide") or "",
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL; is_stranger_ready=False",
        },
        {
            "id": "distinct",
            "ok": True,
            "detail": (
                "distinct from PARTIAL bolt mac-auto (launchd/cron/Shortcuts) — "
                "this is iCloud Drive multi-Mac copy (skips recordings/)"
            ),
        },
        {
            "id": "stranger-ready (never claimed)",
            "ok": False,
            "detail": "William multi-Mac glue — stay PARTIAL",
        },
    ]
    if st.get("error"):
        rows.append({"id": "error", "ok": False, "detail": st["error"]})
    return rows


def try_run(
    *,
    script: str = _DEFAULT_SCRIPT,
    dry_run: bool = True,
    apply: bool = False,
) -> Dict[str, Any]:
    """Dry-run by default. ``--apply`` runs the chosen bash helper (interactive)."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
        "dry_run": bool(dry_run and not apply),
        "apply": bool(apply),
        "script": script,
    }
    st = status(probe=False)
    key = (script or _DEFAULT_SCRIPT).strip().lower()
    if key in ("move_to_icloud", "move-to-icloud", "icloud"):
        key = "move"
    elif key in ("migrate_to_shared", "migrate-to-shared", "shared-hop"):
        key = "shared"
    elif key in ("setup_icloud", "setup-icloud", "second-account"):
        key = "setup"
    if key not in _SCRIPTS:
        out["error"] = _soft(f"unknown script {script!r} — use move|shared|setup")
        return out

    engine = _SCRIPTS[key]
    out["script"] = key
    out["engine"] = str(engine)

    if not engine.is_file():
        out["error"] = _soft(f"missing {engine}")
        return out

    if not st.get("darwin"):
        out["error"] = _soft("not macOS — iCloud helpers skipped")
        return out

    if key == "move" and not st.get("icloud_present"):
        out["error"] = st.get("error") or _soft("iCloud Drive folder missing")
        return out

    intended = f"bash {engine}"
    if out["dry_run"]:
        lines = [
            f"[iCloud] dry-run — would run: {intended}",
            f"  script:   {key} ({engine.name})",
            f"  repo:     {st.get('repo')}",
            f"  iCloud:   {st.get('icloud_root')} present={st.get('icloud_present')}",
            f"  dest:     {st.get('icloud_bolt')} nonempty={st.get('icloud_bolt_nonempty')}",
            f"  note:     no mutation; pass --apply to run (interactive confirm in script)",
            f"  note:     move skips recordings/; leave current checkout in place",
            f"  readiness=PARTIAL · stranger-ready=false · William multi-Mac glue",
        ]
        if st.get("error"):
            lines.append(f"  {st['error']}")
        out["ok"] = True
        out["report"] = "\n".join(lines) + "\n"
        out["would_run"] = intended
        return out

    # apply path — scripts are interactive (read -p); soft-fail on timeout / missing
    try:
        # Inherit stdin/stdout so user can answer y/n
        proc = subprocess.run(
            ["bash", str(engine)],
            cwd=str(_REPO),
            timeout=600,
            check=False,
        )
        out["exit_code"] = int(proc.returncode or 0)
        out["ok"] = proc.returncode == 0
        out["report"] = (
            f"[iCloud] ran {engine.name} (rc={proc.returncode})\n"
            f"  readiness=PARTIAL · stranger-ready=false\n"
        )
        if proc.returncode != 0:
            out["error"] = _soft(f"{engine.name} exit {proc.returncode}")
            out["ok"] = False
            # soft-fail: exit 0 from CLI wrapper still
            out["exit_code"] = 0
        return out
    except subprocess.TimeoutExpired:
        out["error"] = _soft(f"{engine.name} timed out")
        out["ok"] = False
        out["exit_code"] = 0
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["ok"] = False
        out["exit_code"] = 0
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2, default=str))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"icloud readiness: {info.get('readiness')}  ready={ready}")
        print(f"  darwin:   {info.get('darwin')} ({info.get('platform')})")
        print(
            f"  iCloud:   {info.get('icloud_root')}  present={info.get('icloud_present')}"
        )
        print(
            f"  dest:     {info.get('icloud_bolt')}  "
            f"nonempty={info.get('icloud_bolt_nonempty')}"
        )
        print(
            f"  repo:     under_icloud={info.get('repo_under_icloud')}  "
            f"path={info.get('repo')}"
        )
        ep = info.get("engines_present") or {}
        print(
            f"  engines:  move={ep.get('move')} shared={ep.get('shared')} "
            f"setup={ep.get('setup')}"
        )
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}  ({info.get('probe_detail')})")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt icloud",
        description=(
            "Bolt iCloud / multi-Mac sync readiness / list / run "
            "(PARTIAL; soft-fail; William-specific)."
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run"],
        help="status (default) | list | run",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status only: check iCloud Drive + checkout location (soft-fail, no hang)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="run: print intended command only (default when --apply omitted)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="run: actually invoke the bash helper (interactive confirm inside script)",
    )
    parser.add_argument(
        "--script",
        default=_DEFAULT_SCRIPT,
        help="run: move (default) | shared | setup",
    )
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2, default=str))
        else:
            print("iCloud sync pieces (PARTIAL — William multi-Mac; not stranger-ready)")
            for r in rows:
                mark = "OK" if r["ok"] else "--"
                print(f"  [{mark}] {r['id']}: {r['detail']}")
        return 0

    if args.action == "run":
        # Default dry-run unless --apply
        dry = True if not args.apply else False
        if args.dry_run:
            dry = True
        result = try_run(script=args.script, dry_run=dry, apply=args.apply)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(result["error"])
            return 0
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            sys.stdout.write(result.get("report") or "")
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
