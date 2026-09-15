#!/usr/bin/env python3
"""
Migrate_Layout.py — soft-fail CLI for scripts/migrate_layout.py (PARTIAL)
=========================================================================
Safe-by-default drift migrator wrapping ``scripts/migrate_layout.py`` +
``scripts/_layout_rules.py``. Soft-fail prefix: ``Migrate unavailable:``.

CLI (via ``bolt migrate-layout``):
  status [--json] [--probe]
  list   [--json]
  run    [--apply] [--yes] [--dry-run] [--json] [--root PATH]

``run`` without ``--apply`` = dry-run plan (safe default). ``--apply``
performs moves. ``status --probe`` plans only — never applies.

Stay PARTIAL — William layout glue / mutator gated; not stranger-ready.
Distinct from PARTIAL ``bolt layout`` (report-only, never moves) and
READY ``bolt doctor`` / ``bolt verify``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Migrate unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "migrate_layout.py"
_RULES = _REPO / "scripts" / "_layout_rules.py"
_PATHS = _REPO / "scripts" / "_paths.py"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_engine():
    """Import migrate_layout as a module from scripts/."""
    scripts = _REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if not _SCRIPT.is_file():
        raise FileNotFoundError(f"missing engine {_SCRIPT}")
    spec = importlib.util.spec_from_file_location("bolt_migrate_layout", _SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False, root: Optional[str] = None) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt migrate-layout",
        "engine": str(_SCRIPT),
        "rules": str(_RULES),
        "paths_helper": str(_PATHS),
        "repo_root": str(Path(root).resolve() if root else _REPO),
        "engine_present": _SCRIPT.is_file(),
        "rules_present": _RULES.is_file(),
        "paths_present": _PATHS.is_file(),
        "probe": bool(probe),
        "probe_ok": None,
        "planned_ops": None,
        "layout_clean": None,
        "error": "",
        "hint": (
            "safe-by-default layout migrator · dry-run unless --apply · "
            "distinct from bolt layout (report-only) · prefer bolt doctor for audit · "
            "stay PARTIAL (William layout glue)"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/migrate_layout.py")
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
            repo = Path(root).resolve() if root else _REPO
            ops = eng.plan_moves(repo)
            info["probe_ok"] = True
            info["planned_ops"] = len(ops)
            info["layout_clean"] = len(ops) == 0
    except Exception as exc:
        info["ready"] = False
        info["error"] = _soft(str(exc) or type(exc).__name__)
        if probe:
            info["probe_ok"] = False
    return info


def list_items(*, root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Checklist of migrator gates + planned-ops summary (dry plan only)."""
    st = status(probe=True, root=root)
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "rules", "ok": st["rules_present"], "detail": st["rules"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL",
        },
        {
            "id": "safe_default",
            "ok": True,
            "detail": "run without --apply = dry-run; status/probe never apply",
        },
        {
            "id": "distinct_from_layout",
            "ok": True,
            "detail": "bolt layout is report-only; this mutator moves on --apply",
        },
        {
            "id": "planned_ops",
            "ok": st.get("probe_ok") is True,
            "detail": (
                f"planned_ops={st.get('planned_ops')} "
                f"layout_clean={st.get('layout_clean')} "
                f"(dry plan only)"
            ),
        },
    ]
    if st.get("error"):
        rows.append({"id": "error", "ok": False, "detail": st["error"]})
    return rows


def try_run(
    *,
    apply: bool = False,
    yes: bool = False,
    dry_run: bool = False,
    as_json: bool = False,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    """Plan (default) or apply moves. Soft-fails instead of raising."""
    # dry_run flag forces plan-only even if apply was also set
    do_apply = bool(apply) and not bool(dry_run)
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "apply": do_apply,
        "planned_ops": 0,
        "layout_clean": None,
        "report": "",
        "ops": [],
        "repo_root": str(Path(root).resolve() if root else _REPO),
    }
    st = status(probe=False, root=root)
    if not st["ready"]:
        out["error"] = st["error"] or _soft("not ready")
        out["exit_code"] = 0  # soft-fail
        return out
    try:
        eng = _load_engine()
        repo = Path(root).resolve() if root else _REPO
        ops = eng.plan_moves(repo)
        out["ops"] = ops
        out["planned_ops"] = len(ops)
        out["layout_clean"] = len(ops) == 0
        plan_text = eng.render_plan(ops, dry_run=not do_apply)
        if not do_apply:
            out["ok"] = True
            out["exit_code"] = 0
            if as_json:
                out["report"] = json.dumps(
                    {
                        "repo_root": str(repo),
                        "apply": False,
                        "dry_run": True,
                        "count": len(ops),
                        "ops": ops,
                        "plan": plan_text,
                    },
                    indent=2,
                )
            else:
                out["report"] = (
                    plan_text
                    + "\n\nThis was a DRY RUN. No files were touched. "
                    "Re-run with --apply to execute."
                )
            return out

        # --apply path
        rc = eng.apply(ops, assume_yes=bool(yes))
        out["ok"] = rc == 0
        out["exit_code"] = int(rc)
        if as_json:
            out["report"] = json.dumps(
                {
                    "repo_root": str(repo),
                    "apply": True,
                    "count": len(ops),
                    "ops": ops,
                    "exit_code": rc,
                    "plan": plan_text,
                },
                indent=2,
            )
        else:
            suffix = (
                "\nDone. Run 'bolt layout' to confirm the repo is clean."
                if rc == 0
                else "\nMigrate finished with conflicts (exit 1)."
            )
            out["report"] = plan_text + "\n\n=== Applying moves ===\n" + suffix
        return out
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
        print(f"migrate-layout readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine: {_SCRIPT}  present={info.get('engine_present')}")
        print(f"  rules:  {_RULES}  present={info.get('rules_present')}")
        print(f"  paths:  {_PATHS}  present={info.get('paths_present')}")
        if info.get("probe"):
            print(
                f"  probe: clean={info.get('layout_clean')} "
                f"planned_ops={info.get('planned_ops')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt migrate-layout",
        description=(
            "Repo-root layout migrator (PARTIAL; soft-fail; dry-run default)."
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
        help="status only: dry-plan and include planned_ops (never apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="run: actually move files (default is dry-run)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="run --apply: treat destination conflicts as fatal (no prompt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run: force plan-only even if --apply was passed",
    )
    parser.add_argument("--root", default=None, help="override repo root")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = int(e.code) if isinstance(e.code, int) else 0
        if code != 0:
            print(
                _soft(
                    "bad args; try: bolt migrate-layout status | "
                    "bolt migrate-layout run [--apply]"
                ),
                file=sys.stderr,
            )
            return 0
        return 0

    try:
        if args.action == "status":
            return _print_status(
                status(probe=args.probe, root=args.root), args.json
            )

        if args.action == "list":
            rows = list_items(root=args.root)
            if args.json:
                print(json.dumps({"items": rows}, indent=2))
            else:
                for r in rows:
                    mark = "OK" if r["ok"] else "NO"
                    print(f"[{mark}] {r['id']}: {r['detail']}")
            return 0

        if args.action == "run":
            result = try_run(
                apply=args.apply,
                yes=args.yes,
                dry_run=args.dry_run,
                as_json=args.json,
                root=args.root,
            )
            if result.get("error"):
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(result["error"])
                return 0
            if args.json and result.get("report"):
                print(result["report"])
            elif args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result.get("report") or "")
            return int(result.get("exit_code") or 0)
    except Exception as exc:
        print(_soft(str(exc) or type(exc).__name__))
        return 0

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
