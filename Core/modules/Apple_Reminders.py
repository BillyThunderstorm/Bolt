#!/usr/bin/env python3
"""
Apple_Reminders.py — write Bolt briefings into Reminders.app
============================================================
Primary delivery channel from user_profile.json (list name: "Bolt").

Uses JXA via osascript so we do not need EventKit bindings. First run
may prompt for Reminders access; after that it is silent.

Soft-fail CLI (PARTIAL): ``bolt reminders`` status / list / test / send
Prefix: ``Reminders unavailable:``. macOS Reminders.app / TCC gated —
stay PARTIAL (not stranger-ready). ``bolt briefing --send`` still uses
this module.

Public API:
  ensure_list(name)
  create_reminder(title, body="", *, due=None, list_name="Bolt", alert=True)
  replace_today_briefing(actions, *, briefing_path=None, summary="", list_name="Bolt")
  parse_action_items(briefing_text)
  status() / list_items() / try_test() / try_send()
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import platform
import sys
import shutil

DEFAULT_LIST = "Bolt"
BRIEFING_MARKER = "Bolt briefing"
ACTION_PREFIX = "Bolt · "
_SOFT = "Reminders unavailable:"
_REPO = Path(__file__).resolve().parents[2]


def _env_list_name() -> str:
    return (os.getenv("BOLT_REMINDERS_LIST") or DEFAULT_LIST).strip() or DEFAULT_LIST


def parse_action_items(briefing_text: str) -> list[str]:
    """Pull numbered items from the 'Action Items For Today' section."""
    if not briefing_text:
        return []
    lines = briefing_text.splitlines()
    capturing = False
    items: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            capturing = line.lower().startswith("## action items")
            continue
        if not capturing:
            continue
        if line.startswith("---"):
            break
        if not line:
            continue
        # "1. Do the thing" or "- Do the thing"
        if line[0].isdigit() and "." in line[:4]:
            items.append(line.split(".", 1)[1].strip())
        elif line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
    return [i for i in items if i]


def _jxa(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _escape_js(value: str) -> str:
    return json.dumps("" if value is None else str(value))


def ensure_list(name: str = DEFAULT_LIST) -> bool:
    """Create the Reminders list if it is missing. Returns True on success."""
    list_name = name or _env_list_name()
    script = f"""
const app = Application("Reminders");
app.includeStandardAdditions = true;
const name = {_escape_js(list_name)};
const existing = app.lists.whose({{name: name}})();
if (existing.length === 0) {{
    const list = app.List({{name: name}});
    app.lists.push(list);
}}
name;
"""
    try:
        result = _jxa(script)
        return result.returncode == 0
    except Exception:
        return False


def create_reminder(
    title: str,
    body: str = "",
    *,
    due: Optional[datetime] = None,
    list_name: str = DEFAULT_LIST,
    alert: bool = True,
) -> bool:
    """Add one reminder. Best-effort; returns False if Reminders is unavailable."""
    title = (title or "").strip()
    if not title:
        return False
    list_name = list_name or _env_list_name()
    when = due or datetime.now()
    # JXA Date is constructed from a parseable local string.
    due_str = when.strftime("%Y-%m-%dT%H:%M:%S")
    remind_js = "true" if alert else "false"
    script = f"""
const app = Application("Reminders");
const listName = {_escape_js(list_name)};
let lists = app.lists.whose({{name: listName}})();
if (lists.length === 0) {{
    const created = app.List({{name: listName}});
    app.lists.push(created);
    lists = app.lists.whose({{name: listName}})();
}}
const list = lists[0];
const due = new Date({_escape_js(due_str)});
const props = {{
    name: {_escape_js(title[:200])},
    body: {_escape_js(body[:2000])},
    dueDate: due
}};
if ({remind_js}) {{
    props.remindMeDate = due;
}}
list.reminders.push(app.Reminder(props));
"ok";
"""
    try:
        result = _jxa(script)
        return result.returncode == 0
    except Exception:
        return False


def _complete_today_briefing_reminders(list_name: str) -> int:
    """Mark today's previous Bolt briefing reminders complete so re-sends replace them."""
    script = f"""
const app = Application("Reminders");
const listName = {_escape_js(list_name)};
const lists = app.lists.whose({{name: listName}})();
if (lists.length === 0) {{
    0;
}} else {{
    const list = lists[0];
    const today = new Date();
    const y = today.getFullYear();
    const m = today.getMonth();
    const d = today.getDate();
    const marker = {_escape_js(BRIEFING_MARKER)};
    const prefix = {_escape_js(ACTION_PREFIX)};
    let n = 0;
    const rem = list.reminders();
    for (let i = 0; i < rem.length; i++) {{
        const r = rem[i];
        if (r.completed()) continue;
        const name = String(r.name() || "");
        if (name.indexOf(marker) !== 0 && name.indexOf(prefix) !== 0) continue;
        let due = null;
        try {{ due = r.dueDate(); }} catch (e) {{ due = null; }}
        let sameDay = false;
        if (due) {{
            sameDay = due.getFullYear() === y && due.getMonth() === m && due.getDate() === d;
        }} else {{
            sameDay = true;
        }}
        if (sameDay) {{
            r.completed = true;
            n += 1;
        }}
    }}
    n;
}}
"""
    try:
        result = _jxa(script)
        if result.returncode != 0:
            return 0
        return int((result.stdout or "0").strip() or "0")
    except Exception:
        return 0


def replace_today_briefing(
    actions: Iterable[str],
    *,
    briefing_path: Optional[Path] = None,
    summary: str = "",
    list_name: str = DEFAULT_LIST,
    due: Optional[datetime] = None,
    alert: bool = True,
) -> dict:
    """
    Replace today's Bolt briefing reminders with a summary + one item per action.

    Returns a result dict; never raises. Missing Reminders access is reported
    in `error` so callers can fall back to another channel.
    """
    list_name = list_name or _env_list_name()
    items = [str(a).strip() for a in (actions or []) if str(a).strip()]
    when = due or datetime.now()
    path = Path(briefing_path) if briefing_path else None
    path_line = str(path) if path else ""
    file_url = path.resolve().as_uri() if path and path.exists() else path_line

    result = {
        "ok": False,
        "list": list_name,
        "summary": False,
        "actions_created": 0,
        "replaced": 0,
        "error": "",
    }

    if not ensure_list(list_name):
        result["error"] = "Reminders list could not be created (permission?)"
        return result

    result["replaced"] = _complete_today_briefing_reminders(list_name)

    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1)) or "(no action items)"
    body_parts = [
        summary.strip() if summary else "Daily briefing is ready.",
        "",
        numbered,
        "",
        "Open the briefing to review or revise:",
        file_url or path_line,
        "",
        "Queue review: bolt day --decide",
        "Stats: bolt stats",
    ]
    summary_title = f"{BRIEFING_MARKER} ready — {len(items)} action{'s' if len(items) != 1 else ''}"
    result["summary"] = create_reminder(
        summary_title,
        "\n".join(body_parts).strip(),
        due=when,
        list_name=list_name,
        alert=alert,
    )
    # Stagger action due times by 1 minute so Reminders stays readable.
    created = 0
    for i, item in enumerate(items[:8]):
        action_due = when + timedelta(minutes=i + 1)
        ok = create_reminder(
            f"{ACTION_PREFIX}{item}"[:200],
            f"From today's briefing.\n{file_url or path_line}\nRevise or complete, then check this off.",
            due=action_due,
            list_name=list_name,
            alert=False,
        )
        if ok:
            created += 1
    result["actions_created"] = created
    result["ok"] = bool(result["summary"] or created)
    if not result["ok"]:
        result["error"] = result["error"] or "Reminders write failed"
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _osascript_present() -> bool:
    return bool(shutil.which("osascript"))


def _count_open(list_name: str) -> Dict[str, Any]:
    script = f"""
const app = Application("Reminders");
const listName = {_escape_js(list_name)};
const lists = app.lists.whose({{name: listName}})();
if (lists.length === 0) {{
    JSON.stringify({{exists: false, open: 0}});
}} else {{
    const rem = lists[0].reminders();
    let open = 0;
    for (let i = 0; i < rem.length; i++) {{
        if (!rem[i].completed()) open += 1;
    }}
    JSON.stringify({{exists: true, open: open}});
}}
"""
    try:
        result = _jxa(script, timeout=20)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "osascript failed").strip()
            # Keep hints short — never dump the whole JXA script.
            if "not authorized" in err.lower() or "(-1743)" in err:
                err = "Reminders access denied (TCC) — System Settings → Privacy → Reminders"
            elif len(err) > 160:
                err = err[:157] + "..."
            return {"ok": False, "error": err, "exists": False, "open": 0}
        raw = (result.stdout or "").strip() or "{}"
        data = json.loads(raw)
        return {
            "ok": True,
            "exists": bool(data.get("exists")),
            "open": int(data.get("open") or 0),
            "error": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "Reminders probe timed out (permission prompt or app hung?)",
            "exists": False,
            "open": 0,
        }
    except Exception as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            msg = "Reminders probe timed out (permission prompt or app hung?)"
        elif len(msg) > 160:
            msg = msg[:157] + "..."
        return {"ok": False, "error": msg, "exists": False, "open": 0}


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for Apple Reminders delivery (PARTIAL — Darwin / TCC gated)."""
    try:
        list_name = _env_list_name()
        darwin = platform.system() == "Darwin"
        osa = _osascript_present()
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "darwin": darwin,
            "osascript_present": osa,
            "list_name": list_name,
            "list_env": "BOLT_REMINDERS_LIST",
            "briefing_send_path": "bolt briefing --send",
            "cli": "bolt reminders",
            "list_exists": False,
            "open_count": None,
            "probe": bool(probe),
            "probe_ok": None,
            "probe_detail": "",
            "error": "",
            "hint": "",
        }
        if not darwin:
            out["error"] = _soft("not macOS (Reminders.app is Darwin-only)")
            out["hint"] = out["error"]
            return out
        if not osa:
            out["error"] = _soft("osascript missing — cannot talk to Reminders.app")
            out["hint"] = out["error"]
            return out

        # Soft readiness: tooling present. Probe confirms list access.
        out["ready"] = True
        out["hint"] = (
            f"list '{list_name}' · evening inbox via bolt briefing --send · "
            "first run may prompt for Reminders access"
        )

        if probe:
            counted = _count_open(list_name)
            if counted.get("ok"):
                out["probe_ok"] = True
                out["list_exists"] = bool(counted.get("exists"))
                out["open_count"] = counted.get("open")
                if not counted.get("exists"):
                    # ensure_list is write-ish; report missing without creating on status
                    out["probe_detail"] = (
                        f"list '{list_name}' not found yet "
                        "(created on first briefing --send / reminders test)"
                    )
                else:
                    out["probe_detail"] = (
                        f"list '{list_name}' ok · {counted.get('open')} open"
                    )
            else:
                out["probe_ok"] = False
                out["ready"] = False
                detail = counted.get("error") or "Reminders access failed"
                out["probe_detail"] = _soft(detail)
                out["error"] = out["probe_detail"]
                out["hint"] = (
                    out["error"]
                    + " — grant Reminders access in System Settings → Privacy"
                )
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of Reminders delivery pieces (no probe — use status --probe)."""
    try:
        info = status(probe=False)
        rows = [
            ("platform_darwin", bool(info.get("darwin"))),
            ("osascript (JXA)", bool(info.get("osascript_present"))),
            (f"list name ({info.get('list_name')})", True),
            ("bolt briefing --send wired", True),
            ("soft-fail CLI (bolt reminders)", True),
            ("Darwin/TCC gated (stay PARTIAL)", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Apple Reminders (PARTIAL — Darwin / TCC gated)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (list open-count: bolt reminders status --probe)")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_test(*, as_json: bool = False) -> int:
    """Soft-fail write a tiny test reminder (never raises)."""
    try:
        info = status()
        if not info.get("darwin") or not info.get("osascript_present"):
            msg = info.get("error") or _soft("Reminders tooling not ready")
            payload = {"ok": False, "error": msg, "readiness": "PARTIAL"}
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        list_name = info.get("list_name") or _env_list_name()
        if not ensure_list(list_name):
            msg = _soft(
                "could not ensure list (grant Reminders access in System Settings → Privacy)"
            )
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        title = f"{BRIEFING_MARKER} CLI test — bolt reminders"
        ok = create_reminder(
            title,
            "Soft-fail test from bolt reminders test. Safe to complete/delete.",
            list_name=list_name,
            alert=False,
        )
        payload: Dict[str, Any] = {
            "ok": bool(ok),
            "list": list_name,
            "title": title,
            "readiness": "PARTIAL",
        }
        if not ok:
            payload["error"] = _soft(
                "write failed — check Reminders permission / list access"
            )
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            if ok:
                print(f"wrote test reminder on list '{list_name}'")
                print(f"  title: {title}")
                print("  (complete or delete it in Reminders.app)")
            else:
                print(payload["error"], file=sys.stderr)
        return 0
    except Exception as exc:
        msg = _soft(f"test failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_send(message: str, *, as_json: bool = False) -> int:
    """Soft-fail create one reminder from a message string."""
    try:
        text = (message or "").strip()
        if not text:
            msg = _soft("empty message")
            if as_json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        info = status()
        if not info.get("darwin") or not info.get("osascript_present"):
            msg = info.get("error") or _soft("Reminders tooling not ready")
            if as_json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        list_name = info.get("list_name") or _env_list_name()
        if not ensure_list(list_name):
            msg = _soft("could not ensure list (permission?)")
            if as_json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        title = text if text.startswith(ACTION_PREFIX) else f"{ACTION_PREFIX}{text}"
        ok = create_reminder(title[:200], "From bolt reminders send", list_name=list_name, alert=True)
        payload = {"ok": bool(ok), "list": list_name, "title": title[:200], "readiness": "PARTIAL"}
        if not ok:
            payload["error"] = _soft("send failed")
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            if ok:
                print(f"sent → list '{list_name}': {title[:200]}")
            else:
                print(payload["error"], file=sys.stderr)
        return 0
    except Exception as exc:
        msg = _soft(f"send failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Apple Reminders readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  darwin: {info.get('darwin')} · osascript: {info.get('osascript_present')} · "
            f"list: {info.get('list_name')}"
        )
        print(f"  briefing path: {info.get('briefing_send_path')}")
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')} · exists: {info.get('list_exists')} · "
                f"open: {info.get('open_count')}"
            )
            if info.get("probe_detail"):
                print(f"  probe: {info.get('probe_detail')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt reminders — Apple Reminders.app readiness (PARTIAL)

  bolt reminders                                   # status (default)
  bolt reminders status [--json] [--probe]
  bolt reminders list [--json]
  bolt reminders test [--json]
  bolt reminders send "message" [--json]

Soft-fail: "Reminders unavailable:".
Darwin / TCC gated — stay PARTIAL.
bolt briefing --send still writes the Bolt list via this module.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "channels", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("test", "probe-write", "selftest"):
        return try_test(as_json=json_out)
    if cmd in ("send", "add", "create", "write"):
        msg = " ".join(positionals[1:]).strip()
        return try_send(msg, as_json=json_out)
    # Legacy bare-module smoke: treat unknown as send? Prefer help.
    if cmd in ("replace", "briefing-test"):
        sample = [
            "Review the queue (`bolt day --decide`)",
            "Check Apple Reminders for today's briefing",
        ]
        out = replace_today_briefing(
            sample,
            summary="Test briefing from Apple_Reminders.py",
            briefing_path=_REPO / "Docs" / "briefings" / "daily" / "latest_morning.md",
        )
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1

    print(_soft(f"unknown command '{cmd}' — try status|list|test|send"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
