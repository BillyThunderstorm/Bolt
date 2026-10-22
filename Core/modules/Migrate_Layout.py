#!/usr/bin/env python3
"""
Migrate_Layout.py — tidy the top of the Bolt folder (READY)
==========================================================
Safe-by-default drift migrator wrapping ``scripts/migrate_layout.py`` +
``scripts/_layout_rules.py``. Soft-fail prefix: ``Migrate unavailable:``.

CLI (via ``bolt migrate-layout``):
  status [--json] [--probe]
  list   [--json]
  run    [--apply] [--tidy-empty] [--dry-run] [--json] [--root PATH]
  undo   [--json] [--root PATH]

``run`` without ``--apply`` = dry-run plan (safe default). ``--apply``
moves stray files to their home, never overwrites (exact duplicates /
stale leftovers go to the Trash, different files are skipped with the
fix), never prompts, and logs every step to ``Data/layout_moves.jsonl``.
``--tidy-empty`` also trashes empty folders that aren't part of the
layout. ``undo`` puts the last applied run back. ``status --probe``
plans only — never applies.

Distinct from READY ``bolt layout`` (report-only, never moves) and
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
        "partial": False,
        "readiness": "READY",
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
        "last_run": None,
        "log": str((Path(root).resolve() if root else _REPO) / "Data" / "layout_moves.jsonl"),
        "hint": (
            "puts stray top-folder files where bolt layout says they belong · "
            "dry run unless --apply · never overwrites · undo with 'bolt migrate-layout undo'"
        ),
        "is_stranger_ready": True,
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
        repo = Path(root).resolve() if root else _REPO
        log_rows = eng.read_log(repo)
        undone = {r.get("of") for r in log_rows if r.get("action") == "undo"}
        rows = [r for r in log_rows if r.get("action") != "undo"]
        if rows:
            last = rows[-1]["run_id"]
            info["last_run"] = {
                "run_id": last,
                "at": rows[-1].get("at"),
                "steps": sum(1 for r in rows if r["run_id"] == last),
                "undone": last in undone,
            }
        if probe:
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
            "detail": f"prefix {_SOFT!r}",
        },
        {
            "id": "safe_default",
            "ok": True,
            "detail": "run without --apply = dry-run; never overwrites; never prompts; undo available",
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
    tidy_empty: bool = False,
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
        ops = eng.plan_moves(repo, tidy_empty=bool(tidy_empty))
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

        # --apply path (engine prints each step as it goes)
        if not as_json:
            print(plan_text + "\n")
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf) if as_json else contextlib.nullcontext():
            res = eng.apply(ops, assume_yes=bool(yes), repo_root=repo)
        rc = int(res["rc"])
        out["ok"] = not res["failed"]
        out["exit_code"] = rc
        out["run_id"] = res["run_id"]
        summary = (
            f"Done: {len(res['done'])} step(s), {len(res['skipped'])} skipped, "
            f"{len(res['failed'])} failed (run {res['run_id']}). "
            "Undo with 'bolt migrate-layout undo'; check with 'bolt layout run'."
        )
        if as_json:
            out["report"] = json.dumps(
                {
                    "repo_root": str(repo),
                    "apply": True,
                    "run_id": res["run_id"],
                    "done": res["done"],
                    "skipped": res["skipped"],
                    "failed": res["failed"],
                    "exit_code": rc,
                },
                indent=2,
            )
        else:
            out["report"] = "\n" + summary
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
        lr = info.get("last_run")
        print(
            "  last applied run: "
            + (
                f"{lr['run_id']} ({lr['steps']} step(s), {lr['at']}"
                + (", undone" if lr.get("undone") else "")
                + ")"
                if lr
                else "none yet"
            )
        )
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
            "Put stray top-folder files where they belong (READY; dry-run default; undo)."
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run", "undo"],
        help="status (default) | list | run | undo",
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
    parser.add_argument(
        "--tidy-empty",
        action="store_true",
        help="run: also send empty folders that aren't part of the layout to the Trash",
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

        if args.action == "undo":
            eng = _load_engine()
            repo = Path(args.root).resolve() if args.root else _REPO
            res = eng.undo_last(repo)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(res["message"])
                for x in res["left"]:
                    print(f"  left: {x['name']} — {x['why']}")
            return 0

        if args.action == "run":
            result = try_run(
                tidy_empty=args.tidy_empty,
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
