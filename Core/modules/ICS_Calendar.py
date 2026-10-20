#!/usr/bin/env python3
"""
ICS_Calendar.py — local ICS calendar feeds (READY, soft-fail)
=====================================================================
Soft-fail wrapper around ``scripts/generate_calendar.py`` (writes
``Data/calendar/*.ics``). Soft-fail prefix: ``Calendar unavailable:``.

CLI (via ``bolt calendar``):
  status [--json] [--probe]
  list   [--json]
  run    [--dry-run] [--days N] [--output-dir PATH]

READY (19 Oct 2026, Shells): feeds are correct (queue times converted to
America/Chicago, posted/rejected entries skipped, duplicate clip+platform
merged, stable UIDs, RFC 5545 DTSTAMP + line folding, peak windows from
Core/config.json), written atomically, refreshed daily by the 5 PM briefing
cron (which now really attaches scheduled_posts.ics to the briefing email
when posts are coming up). Hosting / webcal subscribe stays optional.
**Distinct from READY Google Calendar OAuth**
via ``bolt gcal`` / ``bolt gcal-auth``. Former thin SCRIPT_MAP ``calendar`` →
``scripts/generate_calendar.py`` (no soft-fail status/list/run). Thumbnails
stay READY via ``bolt thumbnails``.
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

_SOFT = "Calendar unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "generate_calendar.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_OUT = _REPO / "Data" / "calendar"
_QUEUE = _REPO / "Data" / "multi_platform_queue.json"
_FEEDS = (
    "daily_briefing.ics",
    "weekly_insights.ics",
    "peak_hours.ics",
    "scheduled_posts.ics",
)
_STALE_HOURS = 26  # briefing cron refreshes daily at 5 PM


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_engine():
    scripts = _REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing engine {_ENGINE}")
    spec = importlib.util.spec_from_file_location("bolt_generate_calendar", _ENGINE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_ENGINE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _feed_meta() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name in _FEEDS:
        path = _OUT / name
        row: Dict[str, Any] = {
            "name": name,
            "path": str(path),
            "present": path.is_file(),
            "size_bytes": 0,
            "mtime": "",
        }
        row["events"] = 0
        row["age_hours"] = None
        if row["present"]:
            try:
                st = path.stat()
                row["age_hours"] = round(
                    (datetime.now().timestamp() - st.st_mtime) / 3600.0, 1
                )
                text = path.read_text(encoding="utf-8", errors="replace")
                row["events"] = text.count("BEGIN:VEVENT")
                row["valid"] = text.startswith("BEGIN:VCALENDAR") and text.rstrip().endswith("END:VCALENDAR")
                row["size_bytes"] = int(st.st_size)
                row["mtime"] = datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        rows.append(row)
    return rows


def _next_post() -> Optional[Dict[str, str]]:
    """Earliest upcoming event in scheduled_posts.ics (DTSTART is floating
    local time, so a plain string compare against now works)."""
    path = _OUT / "scheduled_posts.ics"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    text = text.replace("\r\n ", "").replace("\n ", "")  # unfold
    now = datetime.now().strftime("%Y%m%dT%H%M%S")
    best = None
    for block in text.split("BEGIN:VEVENT")[1:]:
        start = summary = ""
        for line in block.splitlines():
            if line.startswith("DTSTART"):
                start = line.split(":", 1)[-1].strip()
            elif line.startswith("SUMMARY:"):
                summary = line[8:].replace("\\,", ",").replace("\\;", ";")
        if start and start >= now and (best is None or start < best[0]):
            best = (start, summary)
    if not best:
        return None
    try:
        when = datetime.strptime(best[0][:15], "%Y%m%dT%H%M%S").strftime("%a %b %d %I:%M %p")
    except Exception:
        when = best[0]
    return {"when": when, "summary": best[1]}


def status(*, probe: bool = False) -> Dict[str, Any]:
    feeds = _feed_meta()
    present_count = sum(1 for f in feeds if f["present"])
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt calendar",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "output_dir": str(_OUT),
        "output_dir_present": _OUT.is_dir(),
        "queue_path": str(_QUEUE),
        "queue_present": _QUEUE.is_file(),
        "feeds": feeds,
        "feeds_present_count": present_count,
        "feeds_expected": len(_FEEDS),
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "local ICS feeds under Data/calendar/ · refreshed by the 5 PM "
            "briefing · bolt calendar run to refresh now · import a feed "
            "once (open it in Calendar) · distinct from bolt gcal OAuth"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/generate_calendar.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    info["ready"] = True
    ages = [f["age_hours"] for f in feeds if f.get("age_hours") is not None]
    info["newest_age_hours"] = min(ages) if ages else None
    info["stale"] = (not ages) or min(ages) > _STALE_HOURS
    info["event_counts"] = {f["name"]: f.get("events", 0) for f in feeds}
    info["next_post"] = _next_post()
    if probe:
        try:
            eng = _load_engine()
            info["probe_ok"] = True
            info["has_build_all"] = callable(getattr(eng, "build_all_feeds", None))
            info["engine_output_dir"] = str(getattr(eng, "OUTPUT_DIR", _OUT))
            if not info["has_build_all"]:
                info["probe_ok"] = False
                info["ready"] = False
                info["error"] = _soft("generate_calendar.build_all_feeds missing")
        except Exception as exc:
            info["probe_ok"] = False
            info["ready"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "output_dir",
            "ok": True,
            "detail": (
                f"{st['output_dir']} present={st['output_dir_present']} "
                f"feeds={st['feeds_present_count']}/{st['feeds_expected']}"
            ),
        },
        {
            "id": "queue",
            "ok": True,
            "detail": (
                f"{st['queue_path']} present={st['queue_present']} "
                "(optional; scheduled_posts feed)"
            ),
        },
    ]
    for feed in st.get("feeds") or []:
        rows.append(
            {
                "id": f"feed:{feed['name']}",
                "ok": bool(feed.get("present")),
                "detail": (
                    f"{feed['path']} events={feed.get('events', 0)} "
                    f"size={feed.get('size_bytes', 0)} "
                    f"mtime={feed.get('mtime') or '-'}"
                ),
            }
        )
    rows.append(
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; READY; distinct from READY bolt gcal"
            ),
        }
    )
    return rows


def try_run(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate ICS feeds (or dry-run). Soft-fails instead of raising."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
        "written": {},
        "dry_run": False,
        "output_dir": str(_OUT),
        "lookahead_days": 30,
    }
    st = status(probe=False)
    if not st.get("ready") and st.get("error"):
        out["error"] = st["error"]
        return out

    argv = list(argv or [])
    dry = "--dry-run" in argv or "-n" in argv
    out["dry_run"] = dry

    output_dir: Optional[Path] = None
    days = 30
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--dry-run", "-n"):
            i += 1
            continue
        if arg == "--days" and i + 1 < len(argv):
            try:
                days = int(argv[i + 1])
            except ValueError:
                out["error"] = _soft(f"invalid --days {argv[i + 1]!r}")
                return out
            i += 2
            continue
        if arg.startswith("--days="):
            try:
                days = int(arg.split("=", 1)[1])
            except ValueError:
                out["error"] = _soft(f"invalid {arg!r}")
                return out
            i += 1
            continue
        if arg == "--output-dir" and i + 1 < len(argv):
            output_dir = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--output-dir="):
            output_dir = Path(arg.split("=", 1)[1])
            i += 1
            continue
        # Unknown flag — soft-fail rather than crash
        if arg.startswith("-"):
            out["error"] = _soft(f"unknown flag {arg!r}")
            return out
        i += 1

    out["lookahead_days"] = days
    if output_dir is not None:
        out["output_dir"] = str(output_dir)

    try:
        eng = _load_engine()
        written = eng.build_all_feeds(
            output_dir=output_dir,
            lookahead_days=days,
            dry_run=dry,
        )
        # Normalize paths for JSON
        written_map = {
            k: (str(v) if v is not None else None) for k, v in (written or {}).items()
        }
        out["written"] = written_map
        out["ok"] = True
        if dry:
            keys = ", ".join(written_map.keys()) or "(none)"
            out["report"] = (
                f"[dry-run] would write {len(written_map)} feeds "
                f"({keys}) -> {out['output_dir']}\n"
            )
        else:
            lines = [f"Wrote ICS feeds -> {out['output_dir']}\n"]
            counts: Dict[str, int] = {}
            for key, path in written_map.items():
                n = 0
                try:
                    n = Path(path).read_text(encoding="utf-8").count("BEGIN:VEVENT")
                except Exception:
                    pass
                counts[key] = n
                lines.append(f"  {key}: {n} event(s)  {path}\n")
            out["event_counts"] = counts
            if output_dir is None:
                nxt = _next_post()
                if nxt:
                    lines.append(f"  next post: {nxt['when']} · {nxt['summary']}\n")
                elif counts.get("scheduled_posts", 0) == 0:
                    lines.append(
                        f"  no posts scheduled in the next {days} days "
                        "(queue clips with bolt multi / bolt reprocess)\n"
                    )
            lines.append(
                "  add to Calendar: double-click a .ics in Finder (recurring "
                "feeds only need importing once); the 5 PM briefing email "
                "attaches scheduled_posts.ics when posts are coming up\n"
            )
            out["report"] = "".join(lines)
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["report"] = traceback.format_exc()
        out["exit_code"] = 0  # soft-fail
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"calendar readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:  {_ENGINE}  present={info.get('engine_present')}")
        print(
            f"  output:  {_OUT}  present={info.get('output_dir_present')} "
            f"feeds={info.get('feeds_present_count')}/{info.get('feeds_expected')}"
        )
        print(f"  queue:   {_QUEUE}  present={info.get('queue_present')}")
        counts = info.get("event_counts") or {}
        if counts:
            print("  events:  " + " · ".join(
                f"{k.replace('.ics', '')}={v}" for k, v in counts.items()))
        age = info.get("newest_age_hours")
        if age is not None:
            fresh = "STALE — run bolt calendar run" if info.get("stale") else "fresh"
            print(f"  updated: {age} h ago ({fresh}; 5 PM briefing refreshes daily)")
        nxt = info.get("next_post")
        if nxt:
            print(f"  next post: {nxt['when']} · {nxt['summary']}")
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Back-compat: bare flags → run (former thin SCRIPT_MAP passthrough)
    if argv and argv[0] not in ("status", "list", "run", "-h", "--help"):
        if argv[0].startswith("-"):
            argv = ["run"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt calendar",
        description="Generate local ICS calendar feeds (READY; soft-fail).",
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
        help="status only: import generate_calendar and verify build_all_feeds",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="run only: plan feeds without writing",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="run only: scheduled_posts lookahead days",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="run only: override Data/calendar output",
    )
    args, rest = parser.parse_known_args(argv)

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
        engine_argv = list(rest)
        if args.dry_run and "--dry-run" not in engine_argv and "-n" not in engine_argv:
            engine_argv.append("--dry-run")
        if args.days is not None:
            engine_argv.extend(["--days", str(args.days)])
        if args.output_dir is not None:
            engine_argv.extend(["--output-dir", str(args.output_dir)])
        result = try_run(engine_argv)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
            return 0
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "exit_code": result.get("exit_code"),
                        "dry_run": result.get("dry_run"),
                        "output_dir": result.get("output_dir"),
                        "lookahead_days": result.get("lookahead_days"),
                        "written": result.get("written"),
                        "report": result.get("report"),
                    },
                    indent=2,
                )
            )
        else:
            sys.stdout.write(result.get("report") or "")
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
