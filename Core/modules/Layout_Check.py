#!/usr/bin/env python3
"""
Layout_Check.py — soft-fail CLI for scripts/check_layout.py (PARTIAL)
====================================================================
Report-only repo-root layout audit. Wraps ``scripts/check_layout.py`` +
``scripts/_layout_rules.py``. Soft-fail prefix: ``Layout unavailable:``.

CLI (via ``bolt layout``):
  status [--json] [--probe]
  list   [--json]
  run    [--json] [--quiet] [--root PATH]

Stay PARTIAL — diagnostic only; never moves files; not stranger-ready product.
Distinct from READY ``bolt doctor`` / ``bolt verify``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Layout unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "check_layout.py"
_RULES = _REPO / "scripts" / "_layout_rules.py"
_PATHS = _REPO / "scripts" / "_paths.py"


def _soft(msg: str) -> str:
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_engine():
    """Import check_layout as a module from scripts/ (needs _paths + _layout_rules)."""
    scripts = _REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if not _SCRIPT.is_file():
        raise FileNotFoundError(f"missing engine {_SCRIPT}")
    spec = importlib.util.spec_from_file_location("bolt_check_layout", _SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt layout",
        "engine": str(_SCRIPT),
        "rules": str(_RULES),
        "paths_helper": str(_PATHS),
        "repo_root": str(_REPO),
        "engine_present": _SCRIPT.is_file(),
        "rules_present": _RULES.is_file(),
        "paths_present": _PATHS.is_file(),
        "probe": bool(probe),
        "probe_ok": None,
        "findings_count": None,
        "layout_clean": None,
        "error": "",
        "hint": "report-only root layout audit · never moves files · prefer bolt doctor for live/mocked audit",
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/check_layout.py")
    if not info["rules_present"]:
        missing.append("scripts/_layout_rules.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    try:
        eng = _load_engine()
        info["ready"] = True
        if probe:
            findings = eng.find_misplaced(_REPO)
            info["probe_ok"] = True
            info["findings_count"] = len(findings)
            info["layout_clean"] = len(findings) == 0
    except Exception as exc:
        info["ready"] = False
        info["error"] = _soft(str(exc) or type(exc).__name__)
        if probe:
            info["probe_ok"] = False
    return info


def list_items() -> List[Dict[str, Any]]:
    """Checklist of layout tooling gates."""
    st = status(probe=False)
    rows = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "rules", "ok": st["rules_present"], "detail": st["rules"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL",
        },
        {
            "id": "report_only",
            "ok": True,
            "detail": "never moves/edits/deletes; distinct from bolt doctor",
        },
    ]
    return rows


def try_run(
    *,
    quiet: bool = False,
    as_json: bool = False,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the layout scan. Soft-fails instead of raising."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "findings_count": 0,
        "layout_clean": None,
        "report": "",
        "findings": [],
        "repo_root": str(Path(root).resolve() if root else _REPO),
    }
    st = status(probe=False)
    if not st["ready"]:
        out["error"] = st["error"] or _soft("not ready")
        out["exit_code"] = 0  # soft-fail
        return out
    try:
        eng = _load_engine()
        repo = Path(root).resolve() if root else _REPO
        findings = eng.find_misplaced(repo)
        out["findings"] = findings
        out["findings_count"] = len(findings)
        out["layout_clean"] = len(findings) == 0
        out["ok"] = True
        out["exit_code"] = 0 if not findings else 1
        if as_json:
            out["report"] = json.dumps(
                {
                    "repo_root": str(repo),
                    "ok": not findings,
                    "count": len(findings),
                    "findings": findings,
                },
                indent=2,
            )
        elif quiet:
            status_word = "OK" if not findings else "WARN"
            out["report"] = f"[{status_word}] {len(findings)} misplaced file(s) at {repo}"
        else:
            out["report"] = eng.format_text(findings, repo)
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["exit_code"] = 0
        out["traceback"] = traceback.format_exc(limit=3)
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"layout readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine: {_SCRIPT}  present={info.get('engine_present')}")
        print(f"  rules:  {_RULES}  present={info.get('rules_present')}")
        if info.get("probe"):
            print(
                f"  probe: clean={info.get('layout_clean')} "
                f"findings={info.get('findings_count')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    # soft-fail: always 0 for status unless catastrophic — ready false still 0
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt layout",
        description="Repo-root layout audit (PARTIAL; soft-fail; report only).",
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
        help="status only: run a live scan and include findings_count",
    )
    parser.add_argument("--quiet", action="store_true", help="run: one-line summary")
    parser.add_argument("--root", default=None, help="run: override repo root")
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
        return 0

    if args.action == "run":
        result = try_run(quiet=args.quiet, as_json=args.json, root=args.root)
        if result.get("error"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
            return 0
        if args.json and result.get("report"):
            # report already JSON string when as_json
            print(result["report"])
        elif args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result.get("report") or "")
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
