#!/usr/bin/env python3
"""
modules/Google_Drive_Handbook.py -- Drive/Docs Daily Log for Bolt briefings.

Same OAuth *app* as Google_Calendar.py / Gmail_Briefing.py
(`Core/credentials.json`). Drive-file + Docs scopes are stored in a
separate token file (same pattern as Gmail) so Calendar/Gmail tokens
stay valid.

Non-interactive callers (`bolt briefing` / `bolt morning`) never open a
browser. First-time consent: `bolt drive-auth`.

Readiness:
  - status() / bolt drive status [--json|--probe]
  - Soft-fail "Drive unavailable: …" when credentials/token/libs missing
  - Bare `python -m modules.Google_Drive_Handbook` defaults to status (no browser)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")
        if reason:
            print(f"           Why: {reason}")


_ROOT = Path(__file__).resolve().parent.parent  # Core/
REPO_ROOT = _ROOT.parent
CONFIG_PATH = _ROOT / "config.json"
CREDENTIALS = _ROOT / "credentials.json"
TOKEN_PATH = REPO_ROOT / "Data" / "google_drive_token.json"
_LEGACY_TOKEN = _ROOT / "data" / "google_drive_token.json"
TZ = ZoneInfo("America/Chicago")

if _LEGACY_TOKEN.exists() and not TOKEN_PATH.exists():
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_bytes(_LEGACY_TOKEN.read_bytes())
    except OSError:
        pass

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]

DOC_MIME = "application/vnd.google-apps.document"
FALLBACK_DAILY_OPS = "1wanq-qUUGc4qF-uqtqnajAwLd877qSQ4"


def chicago_today():
    return datetime.now(TZ).date()


def daily_log_title(day=None) -> str:
    day = day or chicago_today()
    return f"{day.isoformat()} Daily Log"


def daily_ops_folder_url(folder_id: str | None = None) -> str:
    fid = folder_id or FALLBACK_DAILY_OPS
    return f"https://drive.google.com/drive/folders/{fid}"


def doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


def skip_line(reason: str, folder_id: str | None = None) -> str:
    return (
        f"Drive Daily Log skipped ({reason}). "
        f"Open {daily_ops_folder_url(folder_id)} — run `bolt drive-auth` once."
    )


def _load_handbook() -> dict:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    hb = cfg.get("google_drive_handbook") or {}
    return hb if isinstance(hb, dict) else {}


def drive_daily_log_enabled(hb: dict | None = None) -> bool:
    """Bolt's own Drive Daily Log create/append switch (default OFF since 2026-10-19).

    Config: google_drive_handbook.drive_daily_log (bool). Env override:
    BOLT_DRIVE_DAILY_LOG=1 forces on, =0 forces off. The real daily logs are
    "Daily Log YYYY-MM-DD" docs made by William's morning routine; this code is
    kept so it can be re-enabled.
    """
    import os

    env = os.getenv("BOLT_DRIVE_DAILY_LOG", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    hb = hb if hb is not None else _load_handbook()
    return bool(hb.get("drive_daily_log", False))


def _daily_ops_id(hb: dict | None = None) -> str:
    hb = hb if hb is not None else _load_handbook()
    folders = hb.get("folders") or {}
    return str(folders.get("02_Daily_Operations") or FALLBACK_DAILY_OPS)


def _get_service(interactive: bool = False):
    """Return (drive, docs) or (None, None). Never opens a browser unless interactive."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        notify(
            "Google Drive/Docs libraries not installed",
            level="warning",
            reason="Run: pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib",
        )
        return None, None

    if not CREDENTIALS.exists():
        return None, None

    creds = None
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            notify("Google Drive token refreshed", level="success")
        except Exception as exc:
            notify(f"Drive token refresh failed: {exc}", level="warning")
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            return None, None
        notify(
            "Opening browser for Google Drive/Docs auth...",
            level="info",
            reason="This only happens once. Sign in and click Allow.",
        )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        notify("Google Drive token saved", level="success", reason=f"Saved to {TOKEN_PATH}")

    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    return drive, docs


def _config_doc_id(hb: dict, day) -> str:
    docs = hb.get("docs") or {}
    key = f"daily_log_{day.isoformat().replace('-', '_')}"
    dated = str(docs.get(key) or "").strip()
    if dated:
        return dated
    today_id = str(docs.get("daily_log_today") or "").strip()
    today_date = str(docs.get("daily_log_today_date") or "").strip()
    if today_id and today_date == day.isoformat():
        return today_id
    return ""


def _remember_daily_log_id(doc_id: str, day) -> None:
    """Store today's Daily Log id in config.json. No secrets."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    hb = cfg.setdefault("google_drive_handbook", {})
    docs = hb.setdefault("docs", {})
    key = f"daily_log_{day.isoformat().replace('-', '_')}"
    docs[key] = doc_id
    docs["daily_log_today"] = doc_id
    docs["daily_log_today_date"] = day.isoformat()
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        notify(f"Could not update config.json with Daily Log id: {exc}", level="warning")


def find_daily_log(drive, folder_id: str, title: str) -> dict | None:
    """Return {id, name} if a Doc with this exact name exists in the folder."""
    safe_title = title.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name = '{safe_title}' and '{folder_id}' in parents "
        f"and mimeType = '{DOC_MIME}' and trashed = false"
    )
    try:
        result = (
            drive.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                pageSize=5,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
    except Exception as exc:
        notify(f"Drive list failed: {exc}", level="warning")
        return None
    files = result.get("files") or []
    if not files:
        return None
    return {"id": files[0]["id"], "name": files[0].get("name") or title}


def create_daily_log(drive, folder_id: str, title: str) -> dict | None:
    try:
        created = (
            drive.files()
            .create(
                body={
                    "name": title,
                    "mimeType": DOC_MIME,
                    "parents": [folder_id],
                },
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception as exc:
        notify(f"Drive create failed: {exc}", level="warning")
        return None
    doc_id = created.get("id")
    if not doc_id:
        return None
    return {"id": doc_id, "name": created.get("name") or title}


def _doc_end_index(docs, doc_id: str) -> int:
    doc = docs.documents().get(documentId=doc_id).execute()
    content = (doc.get("body") or {}).get("content") or []
    if not content:
        return 1
    end = int(content[-1].get("endIndex") or 1)
    # Insert before the terminal newline of the last structural element.
    return max(1, end - 1)


def _doc_plain_text(docs, doc_id: str) -> str:
    try:
        doc = docs.documents().get(documentId=doc_id).execute()
    except Exception:
        return ""
    chunks: list[str] = []
    for el in (doc.get("body") or {}).get("content") or []:
        para = el.get("paragraph") or {}
        for run in para.get("elements") or []:
            chunks.append((run.get("textRun") or {}).get("content") or "")
    return "".join(chunks)


def append_briefing_section(docs, doc_id: str, briefing_text: str) -> bool:
    """Append (or add) a Bolt briefing section via Docs batchUpdate insertText."""
    now = datetime.now(TZ)
    stamp = now.strftime("%Y-%m-%d %-I:%M %p CT").replace(" 0", " ")
    body = (briefing_text or "").strip()
    if not body:
        body = "(empty briefing)"

    existing = _doc_plain_text(docs, doc_id)
    if "Bolt briefing" in existing:
        heading = f"\n\n### Bolt briefing (updated {stamp})\n\n"
    else:
        heading = f"\n\n## Bolt briefing\n\n_First push {stamp}_\n\n"

    payload = heading + body + "\n"
    try:
        index = _doc_end_index(docs, doc_id)
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": index},
                            "text": payload,
                        }
                    }
                ]
            },
        ).execute()
        return True
    except Exception as exc:
        notify(f"Docs append failed: {exc}", level="warning")
        return False


def push_briefing_to_daily_log(
    briefing_text: str,
    *,
    interactive: bool = False,
) -> dict:
    """Find-or-create today's Daily Log and append a briefing section.

    Fail-soft: missing credentials/token never raises. Prints one skip line.
    """
    hb = _load_handbook()
    folder_id = _daily_ops_id(hb)
    day = chicago_today()
    title = daily_log_title(day)

    if not drive_daily_log_enabled(hb):
        msg = "Drive Daily Log off (google_drive_handbook.drive_daily_log=false); local briefing only."
        print(msg)
        return {"ok": False, "skipped": True, "reason": "disabled", "message": msg}

    if not CREDENTIALS.exists():
        msg = skip_line("no Core/credentials.json", folder_id)
        print(msg)
        return {"ok": False, "skipped": True, "reason": "no_credentials", "message": msg}

    drive, docs = _get_service(interactive=interactive)
    if not drive or not docs:
        reason = "not authorized"
        if not TOKEN_PATH.exists():
            reason = "no Drive token"
        msg = skip_line(reason, folder_id)
        print(msg)
        return {"ok": False, "skipped": True, "reason": "no_token", "message": msg}

    found = find_daily_log(drive, folder_id, title)
    created = False
    doc_id = (found or {}).get("id") or ""

    if not doc_id:
        doc_id = _config_doc_id(hb, day)

    if not doc_id:
        created_file = create_daily_log(drive, folder_id, title)
        if not created_file:
            msg = skip_line("could not create Daily Log", folder_id)
            print(msg)
            return {"ok": False, "skipped": True, "reason": "create_failed", "message": msg}
        doc_id = created_file["id"]
        created = True

    if not append_briefing_section(docs, doc_id, briefing_text):
        msg = skip_line("Docs append failed", folder_id)
        print(msg)
        return {
            "ok": False,
            "skipped": True,
            "reason": "append_failed",
            "doc_id": doc_id,
            "message": msg,
        }

    _remember_daily_log_id(doc_id, day)
    url = doc_url(doc_id)
    action = "created" if created else "updated"
    print(f"Drive Daily Log {action}: {url}")
    return {
        "ok": True,
        "created": created,
        "doc_id": doc_id,
        "url": url,
        "title": title,
    }


def authorize() -> int:
    """Interactive consent for Drive-file + Docs. Run from a real Terminal."""
    if not CREDENTIALS.exists():
        print(skip_line("no Core/credentials.json"))
        print(f"Expected: {CREDENTIALS}")
        return 1
    drive, docs = _get_service(interactive=True)
    if not drive or not docs:
        print(skip_line("auth failed"))
        return 1
    print(f"Drive/Docs authorized. Token: {TOKEN_PATH}")
    hb = _load_handbook()
    folder_id = _daily_ops_id(hb)
    title = daily_log_title()
    found = find_daily_log(drive, folder_id, title)
    if found:
        print(f"Today's Daily Log already exists: {doc_url(found['id'])}")
    else:
        cfg_id = _config_doc_id(hb, chicago_today())
        if cfg_id:
            print(f"Config already has today's Daily Log: {doc_url(cfg_id)}")
        else:
            print(f"No '{title}' in 02_Daily_Operations yet — briefing will create it.")
    print(f"Folder: {daily_ops_folder_url(folder_id)}")
    return 0


def status(*, probe: bool = False) -> dict:
    """Return Drive/Docs readiness without opening a browser.

    ready = Core/credentials.json + Data/google_drive_token.json + libs load
    + non-interactive service build succeeds.
    Soft-fail hint always uses "Drive unavailable: …" when not ready.
    """
    hb = _load_handbook()
    folder_id = _daily_ops_id(hb)
    creds_ok = CREDENTIALS.exists()
    token_ok = TOKEN_PATH.exists()
    libs_ok = True
    try:
        from google.oauth2.credentials import Credentials  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError:
        libs_ok = False

    info: dict = {
        "ready": False,
        "credentials_path": str(CREDENTIALS),
        "credentials_exists": creds_ok,
        "token_path": str(TOKEN_PATH),
        "token_exists": token_ok,
        "libraries_installed": libs_ok,
        "daily_ops_folder_id": folder_id,
        "daily_ops_folder_url": daily_ops_folder_url(folder_id),
        "today_title": daily_log_title(),
        "hint": "",
    }

    if not libs_ok:
        info["hint"] = (
            "Drive unavailable: Google API libraries not installed "
            "(pip/uv: google-api-python-client google-auth-httplib2 "
            "google-auth-oauthlib). Briefing still writes local markdown."
        )
        return info
    if not creds_ok:
        info["hint"] = (
            f"Drive unavailable: missing Core/credentials.json "
            f"(expected {CREDENTIALS}). Place OAuth client JSON, then "
            f"`bolt drive-auth`. Briefing still writes local markdown."
        )
        return info
    if not token_ok:
        info["hint"] = (
            "Drive unavailable: no Drive token. Run `bolt drive-auth` once "
            "(browser Allow). Briefing still writes local markdown."
        )
        return info

    drive, docs = _get_service(interactive=False)
    ready = drive is not None and docs is not None
    info["ready"] = ready
    if not ready:
        info["hint"] = (
            "Drive unavailable: token present but not usable "
            "(expired/refresh failed). Re-run `bolt drive-auth`. "
            "Briefing still writes local markdown."
        )
        return info

    info["hint"] = (
        "Drive/Docs ready. Daily Log appends on `bolt briefing` / `bolt morning`. "
        "Try: bolt drive status --probe"
    )

    if probe:
        p = probe_drive()
        info["probe_ok"] = bool(p.get("ok"))
        info["probe_detail"] = p.get("detail") or ""
        if p.get("ok"):
            info["hint"] = p["detail"]
            if p.get("today_doc_url"):
                info["today_doc_url"] = p["today_doc_url"]
        else:
            info["hint"] = p.get("detail") or info["hint"]

    return info


def probe_drive() -> dict:
    """Light Drive list for today's Daily Log. Never opens a browser."""
    result: dict = {"ok": False, "detail": ""}
    drive, docs = _get_service(interactive=False)
    if not drive or not docs:
        result["detail"] = (
            "Drive unavailable: not authorized — run `bolt drive-auth`"
        )
        return result
    hb = _load_handbook()
    folder_id = _daily_ops_id(hb)
    title = daily_log_title()
    try:
        found = find_daily_log(drive, folder_id, title)
        if found:
            url = doc_url(found["id"])
            result["ok"] = True
            result["today_doc_url"] = url
            result["detail"] = f"Drive probe OK — today's Daily Log: {url}"
        else:
            # Folder reachable even if today's doc is not created yet.
            drive.files().list(
                q=(
                    f"'{folder_id}' in parents and trashed=false "
                    f"and mimeType='{DOC_MIME}'"
                ),
                pageSize=1,
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            result["ok"] = True
            result["detail"] = (
                f"Drive probe OK — folder reachable; no '{title}' yet "
                f"(briefing will create it). {daily_ops_folder_url(folder_id)}"
            )
    except Exception as exc:
        result["detail"] = f"Drive unavailable: probe failed ({exc})"
    return result


def _cli_status(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    as_json = "--json" in argv or "-j" in argv
    probe = "--probe" in argv
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("credentials.json:", info["credentials_exists"], info["credentials_path"])
    print("drive_token:", info["token_exists"], info["token_path"])
    print("libraries_installed:", info["libraries_installed"])
    print("daily_ops:", info["daily_ops_folder_url"])
    if TOKEN_PATH.exists():
        try:
            data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            print("token_keys:", sorted(data.keys()))
            scopes = data.get("scopes") or data.get("scope") or []
            if isinstance(scopes, str):
                scopes = scopes.split()
            print("scopes:", list(scopes))
            print("has_refresh_token:", bool(data.get("refresh_token")))
            print("has_access_token:", bool(data.get("token") or data.get("access_token")))
            print("size_bytes:", TOKEN_PATH.stat().st_size)
        except Exception as exc:
            print("token_read_error:", exc)
    print("ready:", info["ready"])
    if probe:
        print("probe_ok:", info.get("probe_ok"))
        if info.get("today_doc_url"):
            print("today_doc_url:", info["today_doc_url"])
    if info.get("hint"):
        print("hint:", info["hint"])
    return 0


def _cli_push() -> int:
    path = REPO_ROOT / "Docs" / "briefings" / "daily" / "latest_morning.md"
    body = path.read_text(encoding="utf-8") if path.exists() else "# Bolt Daily Briefing\n"
    result = push_briefing_to_daily_log(body, interactive=False)
    if not result.get("ok"):
        # Soft-fail message already printed by push_briefing_to_daily_log
        msg = result.get("message") or ""
        if msg and "Drive unavailable:" not in msg and "skipped" in msg.lower():
            # Keep skip_line wording; also surface canonical prefix for tooling.
            print(f"Drive unavailable: {result.get('reason', 'skipped')}")
        return 1
    return 0


def _print_help() -> None:
    print("Usage: python3 -m modules.Google_Drive_Handbook [status|auth|push]")
    print("  status [--json] [--probe]  Credentials/token readiness (default; no browser)")
    print("  auth                       One-time browser consent (or: bolt drive-auth)")
    print("  push                       Append latest morning briefing to today's Daily Log")
    print("CLI: bolt drive status | bolt drive-auth | bolt drive push")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    # Default status — never open a browser on bare `python -m …`
    cmd = args[0] if args else "status"
    rest = args[1:] if args else []
    if cmd in ("auth", "authorize", "login"):
        raise SystemExit(authorize())
    if cmd in ("status", "token-status"):
        raise SystemExit(_cli_status(rest))
    if cmd in ("push", "append"):
        raise SystemExit(_cli_push())
    if cmd in ("-h", "--help", "help"):
        _print_help()
        raise SystemExit(0)
    # Allow `… --json` / `… --probe` without explicit status verb
    if cmd.startswith("-"):
        raise SystemExit(_cli_status(args))
    print(f"Unknown arg: {cmd}")
    _print_help()
    raise SystemExit(2)
