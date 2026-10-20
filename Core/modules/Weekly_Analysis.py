#!/usr/bin/env python3
"""
Weekly_Analysis.py — weekly performance insights (READY)
========================================================
Wraps ``scripts/weekly_analysis.py`` (also run straight from cron every Sunday
9 AM with ``--send``) with a soft-fail CLI.

The engine builds the report from real data (views / platforms / games / top
clips from ``Data/performance_outcomes.jsonl`` with week-over-week, queue
status from ``Data/ready_to_post.json``, clips cut this week, memory hits,
optional Nexus advice fed those numbers), always saves it to
``Data/weekly_reports/weekly_*.md`` (blue Finder tag), and ``--send`` texts a
summary + emails the full report via Bolt_Alerts.

Soft-fail prefix: ``Weekly unavailable:``. Memory / Nexus / alerts optional —
the local markdown report works without them.

Distinct from READY ``bolt analytics`` (outcomes summary), ``bolt briefing``
(daily), and ``bolt stats`` (social pull).

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Weekly unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "weekly_analysis.py"
_CORE = _REPO / "Core"
_DATA = _REPO / "Data"
_OUTCOMES = _DATA / "performance_outcomes.jsonl"
_QUEUE = _DATA / "ready_to_post.json"
_REPORTS = _DATA / "weekly_reports"
_ALERTS_ENV = _DATA / "configs" / "storage_alerts.env"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _engine():
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from scripts import weekly_analysis as wa  # type: ignore

    return wa


def _last_outcome_date() -> str:
    try:
        wa = _engine()
        last = wa.last_outcome()
        dt = wa._parse_ts(last.get("timestamp")) if last else None
        return dt.strftime("%Y-%m-%d") if dt else ""
    except Exception:
        return ""


def _count_outcomes(days: int = 7) -> int:
    if not _OUTCOMES.is_file():
        return 0
    try:
        return len(_engine().load_outcomes(days=days))
    except Exception:
        pass
    try:
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max(1, int(days)))
        n = 0
        with _OUTCOMES.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                ts = str(rec.get("timestamp") or "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", ""))
                    if dt >= cutoff:
                        n += 1
                except Exception:
                    n += 1
        return n
    except Exception:
        return 0


def _queue_total() -> int:
    if not _QUEUE.is_file():
        return 0
    try:
        payload = json.loads(_QUEUE.read_text(encoding="utf-8") or "[]")
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("clips", "items", "ready_to_post"):
                items = payload.get(key)
                if isinstance(items, list):
                    return len(items)
            return 0
    except Exception:
        return 0
    return 0


def _memory_importable() -> bool:
    try:
        if str(_CORE) not in sys.path:
            sys.path.insert(0, str(_CORE))
        from modules.Memory_Index import retrieve_memory  # noqa: F401

        return retrieve_memory is not None
    except Exception:
        return False


def _nexus_importable() -> bool:
    try:
        if str(_CORE) not in sys.path:
            sys.path.insert(0, str(_CORE))
        from modules.Nexus_Creator import NexusCreator  # noqa: F401

        return True
    except Exception:
        return False


def _alerts_importable() -> bool:
    try:
        if str(_CORE) not in sys.path:
            sys.path.insert(0, str(_CORE))
        from modules.Bolt_Alerts import send_sms, send_email  # noqa: F401

        return True
    except Exception:
        return False


def _recent_reports(limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not _REPORTS.is_dir():
        return rows
    try:
        files = sorted(
            (p for p in _REPORTS.glob("weekly_*.md") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return rows
    for p in files[:limit]:
        try:
            st = p.stat()
            rows.append(
                {
                    "path": str(p),
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        st.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "size_bytes": st.st_size,
                }
            )
        except Exception:
            continue
    return rows


def status(*, probe: bool = False, days: int = 7) -> Dict[str, Any]:
    """Readiness for weekly performance insights (READY)."""
    try:
        script_ok = _SCRIPT.is_file()
        outcomes_ok = _OUTCOMES.is_file()
        queue_ok = _QUEUE.is_file()
        mem_ok = _memory_importable()
        nexus_ok = _nexus_importable()
        alerts_ok = _alerts_importable()
        alerts_env = _ALERTS_ENV.is_file()
        recent = _recent_reports(5)
        outcome_count = _count_outcomes(days=days)
        last_logged = _last_outcome_date()
        queue_total = _queue_total()

        reports_writable = False
        reports_ok = _REPORTS.is_dir()
        try:
            _REPORTS.mkdir(parents=True, exist_ok=True)
            probe_file = _REPORTS / ".bolt_weekly_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            reports_writable = True
            reports_ok = True
        except Exception:
            reports_writable = False

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "outcomes_path": str(_OUTCOMES),
            "outcomes_present": outcomes_ok,
            "outcomes_last_days": int(days),
            "outcomes_count": outcome_count,
            "last_outcome_date": last_logged,
            "queue_path": str(_QUEUE),
            "queue_present": queue_ok,
            "queue_total": queue_total,
            "memory_importable": mem_ok,
            "nexus_importable": nexus_ok,
            "alerts_importable": alerts_ok,
            "alerts_env_present": alerts_env,
            "reports_dir": str(_REPORTS),
            "reports_present": reports_ok,
            "reports_writable": reports_writable,
            "recent_count": len(recent),
            "recent": recent,
            "cli": "bolt weekly",
            "note": (
                "Weekly report from logged views + queue + clips cut + memory + optional Nexus; "
                "saved to Data/weekly_reports; --send texts summary + emails report; "
                "distinct from bolt analytics / briefing / stats"
            ),
            "is_stranger_ready": True,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT})")
            out["hint"] = out["error"]
            return out

        if not reports_writable:
            out["error"] = _soft(f"reports dir not writable ({_REPORTS})")
            out["hint"] = out["error"]
            return out

        # Ready: script + writable reports. Thin outcomes / missing
        # memory / Nexus still produce a useful local markdown report.
        out["ready"] = True
        bits = [
            f"{outcome_count} outcome(s) in last {days}d"
            + (f" (last logged {last_logged})" if last_logged else ""),
            f"queue={queue_total}",
            f"memory={'ok' if mem_ok else 'degraded'}",
            f"nexus={'ok' if nexus_ok else 'skip'}",
        ]
        out["hint"] = (
            "ok — " + "; ".join(bits) + "; run: bolt weekly run [--send] [--days N] [--no-ai]"
        )
        if not outcome_count:
            out["hint"] += (
                " · no views logged this window — `bolt stats` (YouTube) / "
                "`bolt log-perf` (TikTok/X) fill it in"
            )
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "cli": "bolt weekly",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of weekly analysis pieces (no report generation)."""
    try:
        info = status(probe=False)
        recent = info.get("recent") or []
        rows = [
            ("script weekly_analysis.py", bool(info.get("script_present"))),
            ("Data/performance_outcomes.jsonl", bool(info.get("outcomes_present"))),
            (f"outcomes last {info.get('outcomes_last_days')}d ({info.get('outcomes_count')})", True),
            (f"Data/ready_to_post.json ({info.get('queue_total')} clips)", bool(info.get("queue_present"))),
            ("Memory_Index importable", bool(info.get("memory_importable"))),
            ("Nexus_Creator importable (optional)", bool(info.get("nexus_importable"))),
            ("Bolt_Alerts importable (--send)", bool(info.get("alerts_importable"))),
            ("storage_alerts.env (SMS/email)", bool(info.get("alerts_env_present"))),
            (f"reports dir ({info.get('reports_dir')})", bool(info.get("reports_present"))),
            ("reports writable", bool(info.get("reports_writable"))),
            ("soft-fail CLI (bolt weekly)", True),
            ("Memory/Nexus/alerts optional (report still saves)", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "READY",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "recent": recent,
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Weekly analysis (READY)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if recent:
            print("  recent:")
            for r in recent[:5]:
                print(f"    - {r.get('name')} ({r.get('mtime')})")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt weekly run [--send] [--days N] [--no-ai])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def _parse_days(extra: Optional[List[str]]) -> int:
    days = 7
    if not extra:
        return days
    for i, a in enumerate(extra):
        if a == "--days" and i + 1 < len(extra):
            try:
                days = int(extra[i + 1])
            except Exception:
                pass
            break
        m = re.match(r"^--days=(\d+)$", a)
        if m:
            try:
                days = int(m.group(1))
            except Exception:
                pass
    return max(1, days)


def try_run(
    *,
    as_json: bool = False,
    dry_run: bool = False,
    print_only: bool = True,
    send: bool = False,
    days: int = 7,
    use_ai: bool = True,
) -> int:
    """Soft-fail run of weekly_analysis.py (never raises). The engine saves markdown under Data/weekly_reports/."""
    try:
        info = status(probe=False, days=days)
        if not info.get("script_present"):
            msg = info.get("error") or _soft("engine script missing")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("ready"):
            msg = info.get("error") or _soft("weekly tooling not ready")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        argv = [str(_SCRIPT), "--days", str(int(days))]
        # Always --print so we capture/save real markdown (engine otherwise
        # only prints "Weekly report generated.").
        argv.append("--print")
        if send:
            argv.append("--send")
        if not use_ai:
            argv.append("--no-ai")

        if dry_run:
            payload = {
                "ok": True,
                "readiness": "READY",
                "dry_run": True,
                "would_run": argv,
                "reports_dir": str(_REPORTS),
                "cwd": str(_REPO),
                "days": int(days),
                "send": bool(send),
            }
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"[dry-run] would run: {' '.join(argv)}")
                print(f"  cwd: {_REPO}")
                print(f"  reports: {_REPORTS}")
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = str(_CORE) + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        py = sys.executable
        try:
            proc = subprocess.run(
                [py] + argv,
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            msg = _soft("weekly timed out after 300s")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        except Exception as exc:
            msg = _soft(f"run failed ({exc})")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        # Engine may print "Nexus enrichment skipped: …" on stderr or stdout;
        # keep the markdown body for save/print.
        # The engine saves the report itself (so the Sunday cron keeps one
        # too) and prints "Weekly report saved: <path>"; pick that up instead
        # of writing a second copy.
        saved: Optional[str] = None
        send_line = ""
        body_lines = []
        for line in stdout.splitlines():
            if line.startswith("Weekly report saved: "):
                saved = line.split(": ", 1)[1].strip()
            elif line.startswith("Weekly send: "):
                send_line = line.strip()
            elif line.startswith("Weekly report generated"):
                continue
            else:
                body_lines.append(line)
        report = "\n".join(body_lines).strip()
        if not report and stderr.strip():
            report = stderr.strip()

        if proc.returncode != 0 and not report:
            err_tail = (stderr or stdout).strip()[-400:]
            msg = _soft(
                f"engine exited {proc.returncode}"
                + (f": {err_tail}" if err_tail else "")
            )
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "error": msg,
                            "readiness": "READY",
                            "output": saved,
                        },
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        if as_json:
            print(
                json.dumps(
                    {
                        "ok": bool(saved),
                        "readiness": "READY",
                        "output": saved,
                        "send_result": send_line,
                        "reports_dir": str(_REPORTS),
                        "days": int(days),
                        "send": bool(send),
                        "report_chars": len(report),
                        "stdout_tail": report[-1200:] if report else "",
                        "stderr_tail": stderr.strip()[-400:] if stderr else "",
                    },
                    indent=2,
                )
            )
        else:
            if report:
                print(report)
            if saved:
                print(f"\nWeekly report saved: {saved}")
            else:
                print(_soft("report was not saved — check Data/weekly_reports permissions"), file=sys.stderr)
            if send:
                print(send_line or "(send attempted via Bolt_Alerts — see bolt alerts status)")
        return 0
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, "readiness": "READY"},
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False, days: int = 7) -> int:
    try:
        info = status(probe=probe, days=days)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print(f"Weekly analysis readiness ({info.get('readiness')})")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  script: {info.get('script_present')} · outcomes: {info.get('outcomes_count')} "
            f"(last {info.get('outcomes_last_days')}d"
            + (f"; last logged {info.get('last_outcome_date')}" if info.get("last_outcome_date") else "")
            + f") · queue: {info.get('queue_total')}"
        )
        print(
            f"  memory: {info.get('memory_importable')} · nexus: {info.get('nexus_importable')} · "
            f"alerts: {info.get('alerts_importable')}"
        )
        print(
            f"  reports: {info.get('reports_dir')} "
            f"(writable={info.get('reports_writable')}, prior={info.get('recent_count')})"
        )
        print(f"  note: {info.get('note')}")
        print(f"  soft_fail_prefix: {info.get('soft_fail_prefix')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ready": False, "error": msg, "readiness": "READY"},
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt weekly — weekly performance insights (READY)

  bolt weekly                               # status (default)
  bolt weekly status [--json] [--probe] [--days N]
  bolt weekly list [--json]
  bolt weekly run [--json] [--dry-run] [--send] [--days N] [--no-ai]
  bolt weekly print|--print [--days N]      # same as run (prints + saves)
  bolt weekly send|--send [--days N]        # run + text summary + email full report

Report: views/platforms/games/top clips (week-over-week), queue status,
clips cut this week, memory, Nexus advice (skip with --no-ai).
Always saved to Data/weekly_reports/weekly_*.md (blue Finder tag).
Soft-fail: "Weekly unavailable:".
Distinct from bolt analytics (outcomes), bolt briefing (daily), bolt stats (social).
Engine: scripts/weekly_analysis.py → Data/weekly_reports/
Aliases: monthly, week-insights, weekly-analysis, weekly-status
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "--dryrun" in args
    send_flag = "--send" in args
    print_flag = "--print" in args
    no_ai = "--no-ai" in args
    days = _parse_days(args)
    # Drop flags and the value that belongs to --days so "7" is never a verb.
    cleaned: list[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a.startswith("-"):
            if a == "--days":
                skip_next = True
            continue
        cleaned.append(a)

    if not cleaned:
        # Preserve legacy: `bolt weekly --print` / `--send` without a verb
        if print_flag or send_flag:
            return try_run(
                as_json=json_out,
                dry_run=dry_run,
                print_only=True,
                send=send_flag,
                days=days,
                use_ai=no_ai is False,
            )
        return print_status(as_json=json_out, probe=probe, days=days)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe, days=days)
    if cmd in ("list", "ls", "recent", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "generate", "report", "insights", "analyze"):
        return try_run(
            as_json=json_out,
            dry_run=dry_run,
            print_only=True,
            send=send_flag,
            days=days,
            use_ai=no_ai is False,
        )
    if cmd in ("print", "show"):
        return try_run(
            as_json=json_out,
            dry_run=dry_run,
            print_only=True,
            send=False,
            days=days,
            use_ai=no_ai is False,
        )
    if cmd in ("send", "email", "sms"):
        return try_run(
            as_json=json_out,
            dry_run=dry_run,
            print_only=True,
            send=True,
            days=days,
            use_ai=no_ai is False,
        )

    print(
        _soft(f"unknown command '{cmd}' — try status|list|run|print|send"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
