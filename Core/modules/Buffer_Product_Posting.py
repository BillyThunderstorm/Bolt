#!/usr/bin/env python3
"""Schedule an approved product cut on Buffer. No second confirmation.

Standing rule: Data/configs/buffer_product_posting.json
Video Editor and Bolt both read that file. William's approval of the
finished product cut is the only yes. Bolt then queues TikTok
@itssimplybilly and the YouTube Shorts channel named in the rule.

Buffer's createPost mutation needs a public https video URL and
BUFFER_ACCESS_TOKEN. A local file or a missing token still writes
Data/buffer_product_queue.json with an honest status. This module
never invents a token or a channel id.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
RULE_FILE = REPO_ROOT / "Data" / "configs" / "buffer_product_posting.json"
QUEUE_FILE = REPO_ROOT / "Data" / "buffer_product_queue.json"
CATALOG_FILE = REPO_ROOT / "Data" / "content" / "catalog.json"
DEFAULT_API_URL = "https://api.buffer.com"

Poster = Callable[[str, str, dict], dict]

_ENV_LOADED = False

ACCOUNT_ORGS_QUERY = """
query AccountOrgs {
  account {
    organizations { id name }
  }
}
"""

CHANNELS_QUERY = """
query GetChannels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    displayName
    service
  }
}
"""

CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post { id dueAt }
    }
    ... on MutationError {
      message
    }
  }
}
"""


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED or load_dotenv is None:
        _ENV_LOADED = True
        return
    for name in (".env.local", ".env"):
        path = REPO_ROOT / name
        if path.exists():
            load_dotenv(path, override=False)
    _ENV_LOADED = True


def access_token() -> str:
    """Return BUFFER_ACCESS_TOKEN, or empty when William has not set one."""
    _load_env()
    return os.getenv("BUFFER_ACCESS_TOKEN", "").strip()


def load_rule() -> dict:
    """Read the standing product-posting rule. Empty dict if it is missing."""
    if not RULE_FILE.exists():
        return {}
    try:
        data = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_queue() -> dict:
    if not QUEUE_FILE.exists():
        return {"items": []}
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}
    if not isinstance(data, dict):
        return {"items": []}
    data.setdefault("items", [])
    return data


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm(value: str) -> str:
    text = str(value or "").strip().casefold()
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("`", "'")
    )


def _handle_key(value: str) -> str:
    return _norm(value).lstrip("@").replace(" ", "")


def _public_https(url: str) -> str:
    text = str(url or "").strip()
    if text.lower().startswith("https://"):
        return text
    return ""


def _safe(text: str, token: str) -> str:
    cleaned = str(text or "")
    if token and token in cleaned:
        cleaned = cleaned.replace(token, "[redacted]")
    return cleaned[:500]


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    """POST one GraphQL document to Buffer. Never includes the token in errors."""
    if requests is None:
        return {"ok": False, "error": "requests is not installed"}
    api_url = os.getenv("BUFFER_API_URL", "").strip() or DEFAULT_API_URL
    try:
        response = requests.post(
            api_url,
            json={"query": query, "variables": variables or {}},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "error": _safe(str(exc), token)}
    try:
        body = response.json()
    except Exception:
        return {
            "ok": False,
            "error": f"Buffer HTTP {response.status_code} (response was not JSON)",
        }
    if response.status_code >= 400:
        message = ""
        if isinstance(body, dict):
            errors = body.get("errors") or []
            if errors and isinstance(errors, list):
                message = str((errors[0] or {}).get("message") or "")
        detail = message or f"Buffer HTTP {response.status_code}"
        return {"ok": False, "error": _safe(detail, token), "body": body}
    if isinstance(body, dict) and body.get("errors"):
        message = str((body["errors"][0] or {}).get("message") or "Buffer GraphQL error")
        return {"ok": False, "error": _safe(message, token), "body": body}
    return {"ok": True, "body": body if isinstance(body, dict) else {}}


def _find_catalog_item(catalog: dict, name: str) -> dict | None:
    items = catalog.get("items") or []
    needle = name.strip().casefold()
    if not needle:
        return None
    for item in items:
        if str(item.get("id") or "").casefold() == needle:
            return item
    for item in items:
        if str(item.get("name") or "").casefold() == needle:
            return item
    hits = [
        item
        for item in items
        if needle in str(item.get("name") or "").casefold()
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _load_catalog(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}
    if not isinstance(data, dict):
        return {"items": []}
    data.setdefault("items", [])
    return data


def _caption(title: str, script: str, limit: int = 2200) -> str:
    body = (script or "").strip() or title.strip() or "Honest product take."
    if "disclosure" not in body.casefold():
        body = f"{body}\n\nDisclosure: honest opinion; links may earn a commission."
    return body[:limit].rstrip()


def _match_channel(wanted: dict, rows: list[dict]) -> dict | None:
    service = str(wanted.get("service") or "").casefold()
    handle = _handle_key(wanted.get("handle") or "")
    display = _norm(wanted.get("display_name") or "")
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_service = str(row.get("service") or "").casefold()
        if service and row_service != service:
            continue
        row_handle = _handle_key(row.get("name") or "")
        shown = _norm(row.get("displayName") or "")
        plain = _norm(row.get("name") or "")
        if handle and handle == row_handle:
            return row
        if display and display in {shown, plain}:
            return row
    return None


def _resolve_channel_ids(
    token: str,
    channels: list[dict],
    organization_id: str,
    poster: Poster,
) -> str:
    """Fill blank channel ids from Buffer. Returns an error string, or ""."""
    if all(str(ch.get("buffer_channel_id") or "").strip() for ch in channels):
        return ""
    org_ids: list[str] = []
    if organization_id:
        org_ids.append(organization_id)
    else:
        found = poster(token, ACCOUNT_ORGS_QUERY, {})
        if not found.get("ok"):
            return str(found.get("error") or "could not list Buffer organizations")
        orgs = ((found.get("body") or {}).get("data") or {}).get("account", {})
        orgs = (orgs or {}).get("organizations") or []
        org_ids = [str(org.get("id")) for org in orgs if isinstance(org, dict) and org.get("id")]
        if not org_ids:
            return "Buffer account returned no organizations"
    rows: list[dict] = []
    errors: list[str] = []
    for org_id in org_ids:
        found = poster(token, CHANNELS_QUERY, {"organizationId": org_id})
        if not found.get("ok"):
            errors.append(str(found.get("error") or "channel lookup failed"))
            continue
        batch = ((found.get("body") or {}).get("data") or {}).get("channels") or []
        rows.extend(row for row in batch if isinstance(row, dict))
    for channel in channels:
        if str(channel.get("buffer_channel_id") or "").strip():
            continue
        match = _match_channel(channel, rows)
        if match and match.get("id"):
            channel["buffer_channel_id"] = str(match["id"])
            channel["resolved_from"] = "buffer_api"
    if errors and not rows:
        return errors[0]
    return ""


def _metadata(rule: dict, channel: dict, title: str) -> dict:
    service = str(channel.get("service") or "").casefold()
    if service == "youtube":
        category = str(rule.get("youtube_category_id") or "26")
        return {
            "youtube": {
                "title": (title or channel.get("label") or "Product take")[:100],
                "categoryId": category,
                "privacy": "public",
                "madeForKids": False,
            }
        }
    if service == "tiktok":
        return {"tiktok": {"title": (title or "")[:150]}}
    return {}


def _create_post(
    token: str,
    rule: dict,
    channel: dict,
    text: str,
    video_url: str,
    title: str,
    poster: Poster,
) -> dict:
    variables = {
        "input": {
            "text": text,
            "channelId": channel["buffer_channel_id"],
            "schedulingType": rule.get("scheduling_type") or "automatic",
            "mode": rule.get("mode") or "addToQueue",
            "assets": [{"video": {"url": video_url}}],
            "metadata": _metadata(rule, channel, title),
        }
    }
    # schedulingType automatic + mode addToQueue is the schedule.
    # needsApproval is omitted on purpose: that flag would ask again.
    result = poster(token, CREATE_POST_MUTATION, variables)
    if not result.get("ok"):
        return {"ok": False, "error": str(result.get("error") or "Buffer request failed")}
    payload = ((result.get("body") or {}).get("data") or {}).get("createPost") or {}
    post = payload.get("post") or {}
    if post.get("id"):
        return {"ok": True, "id": str(post["id"]), "due_at": post.get("dueAt") or ""}
    message = str(payload.get("message") or "Buffer did not return a post id")
    return {"ok": False, "error": _safe(message, token)}


def _rollup(channels: list[dict]) -> str:
    statuses = [str(ch.get("status") or "") for ch in channels]
    if statuses and all(status == "scheduled" for status in statuses):
        return "scheduled"
    order = (
        "held_for_confirmation",
        "awaiting_buffer_credentials",
        "awaiting_public_video_url",
        "awaiting_channel_id",
        "buffer_error",
    )
    for status in order:
        if status in statuses:
            return status
    return statuses[0] if statuses else "buffer_error"


def _detail_for(status: str, extra: str = "") -> str:
    messages = {
        "scheduled": "Buffer accepted the post and queued it. No second confirmation.",
        "awaiting_buffer_credentials": (
            "BUFFER_ACCESS_TOKEN is empty. The job is queued for both channels "
            "and will be sent when the token is in .env.local. No token was invented."
        ),
        "awaiting_public_video_url": (
            "Buffer createPost needs a public https video URL. The local cut is "
            "recorded and was not uploaded."
        ),
        "awaiting_channel_id": (
            "buffer_channel_id is blank and Buffer did not match this channel yet. "
            "Video Editor can paste the id into Data/configs/buffer_product_posting.json."
        ),
        "held_for_confirmation": (
            "confirmations_after_approval is not 0, so Bolt did not send this to Buffer."
        ),
        "buffer_error": extra or "Buffer returned an error. The job is still queued.",
    }
    base = messages.get(status, extra or status)
    if extra and status not in {"buffer_error"}:
        return f"{base} {extra}".strip()
    return base


def _merge_channels(previous: list[dict], rule: dict) -> list[dict]:
    old = {str(ch.get("key")): ch for ch in previous or []}
    merged = []
    for spec in rule.get("channels") or []:
        key = str(spec.get("key") or "")
        prev = old.get(key) or {}
        configured = str(spec.get("buffer_channel_id") or "").strip()
        remembered = str(prev.get("buffer_channel_id") or "").strip()
        merged.append(
            {
                "key": key,
                "platform": spec.get("platform") or "",
                "service": spec.get("service") or "",
                "handle": spec.get("handle") or "",
                "display_name": spec.get("display_name") or "",
                "label": spec.get("label")
                or spec.get("display_name")
                or spec.get("handle")
                or key,
                "buffer_channel_id": configured or remembered,
                "resolved_from": prev.get("resolved_from") or "",
                "status": prev.get("status") or "",
                "buffer_post_id": prev.get("buffer_post_id") or "",
                "due_at": prev.get("due_at") or "",
                "detail": prev.get("detail") or "",
            }
        )
    return merged


def _find_job(name: str, video_path: str, video_url: str) -> dict | None:
    needle = name.strip().casefold()
    for job in load_queue().get("items") or []:
        if str(job.get("product_name") or "").casefold() != needle:
            continue
        same_file = video_path and job.get("video_path") == video_path
        same_url = video_url and job.get("video_url") == video_url
        if same_file or same_url:
            return job
    return None


def _resolve_media(video_path: str, video_url: str) -> tuple[str, str, str]:
    """Return (local_path, https_url, error). A public URL does not require a local file."""
    public = _public_https(video_url) or _public_https(video_path)
    local_raw = str(video_path or "").strip()
    if _public_https(local_raw):
        local_raw = ""
    if local_raw:
        path = Path(local_raw).expanduser()
        if path.is_file():
            return str(path.resolve()), public, ""
        if public:
            return str(path), public, ""
        return str(path), "", f"Video not found: {path}"
    if public:
        return "", public, ""
    return "", "", "No video path or https URL was given."


def _stamp_catalog(
    catalog_path: Path,
    catalog: dict,
    item: dict,
    job: dict,
    video_ref: str,
) -> None:
    draft = item.get("last_draft")
    if not isinstance(draft, dict):
        draft = {}
        item["last_draft"] = draft
    draft["cut_approved_at"] = job.get("updated_at") or _now()
    draft["cut_approved_by"] = "William"
    draft["cut_video"] = video_ref
    draft["buffer_job_id"] = job.get("id")
    draft["buffer_status"] = job.get("status")
    item["buffer_job_id"] = job.get("id")
    item["buffer_status"] = job.get("status")
    _save_json(catalog_path, catalog)


def _attempt_send(
    job: dict,
    rule: dict,
    title: str,
    script: str,
    poster: Poster,
) -> None:
    channels: list[dict] = job.get("channels") or []
    if int(rule.get("confirmations_after_approval", 0) or 0) != 0:
        for channel in channels:
            channel["status"] = "held_for_confirmation"
            channel["detail"] = _detail_for("held_for_confirmation")
        job["status"] = "held_for_confirmation"
        job["detail"] = _detail_for("held_for_confirmation")
        return

    token = access_token()
    video_url = _public_https(job.get("video_url") or "")
    lookup_error = ""
    if token:
        lookup_error = _resolve_channel_ids(
            token,
            channels,
            str(rule.get("buffer_organization_id") or os.getenv("BUFFER_ORGANIZATION_ID", "")).strip(),
            poster,
        )
    text = _caption(title, script)
    for channel in channels:
        if channel.get("buffer_post_id"):
            channel["status"] = "scheduled"
            channel["detail"] = _detail_for("scheduled")
            continue
        if not token:
            channel["status"] = "awaiting_buffer_credentials"
            channel["detail"] = _detail_for("awaiting_buffer_credentials")
            continue
        if not video_url:
            channel["status"] = "awaiting_public_video_url"
            channel["detail"] = _detail_for("awaiting_public_video_url")
            continue
        if not str(channel.get("buffer_channel_id") or "").strip():
            channel["status"] = "awaiting_channel_id"
            channel["detail"] = _detail_for("awaiting_channel_id", lookup_error)
            continue
        sent = _create_post(token, rule, channel, text, video_url, title, poster)
        if sent.get("ok"):
            channel["status"] = "scheduled"
            channel["buffer_post_id"] = sent.get("id") or ""
            channel["due_at"] = sent.get("due_at") or ""
            channel["detail"] = _detail_for("scheduled")
        else:
            channel["status"] = "buffer_error"
            channel["detail"] = _detail_for("buffer_error", str(sent.get("error") or ""))
    job["status"] = _rollup(channels)
    extras = [ch.get("detail") or "" for ch in channels if ch.get("detail")]
    job["detail"] = _detail_for(job["status"])
    if job["status"] == "buffer_error" and extras:
        job["detail"] = extras[0]


def schedule_approved_product_cut(
    name: str,
    video_path: str = "",
    *,
    title: str | None = None,
    video_url: str | None = None,
    caption: str | None = None,
    catalog_path: Path | None = None,
    poster: Poster | None = None,
) -> dict:
    """Record William's approval and schedule both Buffer channels.

    Returns the queue job. `ok` is true when the job is saved, including
    when Buffer cannot be called yet. `scheduled` is true only after
    createPost succeeds for every channel.
    """
    rule = load_rule()
    if not rule:
        return {
            "ok": False,
            "scheduled": False,
            "status": "rule_missing",
            "detail": f"Missing standing rule: {RULE_FILE}",
        }
    if not rule.get("enabled", True):
        return {
            "ok": False,
            "scheduled": False,
            "status": "rule_disabled",
            "detail": "buffer_product_posting.json has enabled=false. Nothing was queued.",
        }
    if str(rule.get("trigger") or "") != "product_cut_approved":
        return {
            "ok": False,
            "scheduled": False,
            "status": "rule_trigger_mismatch",
            "detail": "This rule does not trigger on product_cut_approved.",
        }

    local_path, public_url, media_error = _resolve_media(video_path or "", video_url or "")
    if media_error:
        return {
            "ok": False,
            "scheduled": False,
            "status": "video_missing",
            "detail": media_error,
            "product_name": name,
        }

    catalog_file = Path(catalog_path) if catalog_path else CATALOG_FILE
    catalog = _load_catalog(catalog_file)
    item = _find_catalog_item(catalog, name)
    draft = (item or {}).get("last_draft") if isinstance((item or {}).get("last_draft"), dict) else {}
    resolved_title = (title or "").strip() or str((item or {}).get("name") or name).strip()
    script = caption if caption is not None else str((draft or {}).get("script") or "")

    existing = _find_job(name, local_path, public_url)
    now = _now()
    if existing:
        job = existing
        job["updated_at"] = now
    else:
        job = {
            "id": uuid.uuid4().hex[:8],
            "created_at": now,
            "updated_at": now,
            "trigger": "product_cut_approved",
            "confirmations_after_approval": int(rule.get("confirmations_after_approval", 0) or 0),
            "via": "buffer",
            "product_name": name.strip(),
            "catalog_id": (item or {}).get("id") or "",
            "title": resolved_title,
            "video_path": local_path,
            "video_url": public_url,
            "channels": [],
        }
    job["title"] = resolved_title
    job["catalog_id"] = (item or {}).get("id") or job.get("catalog_id") or ""
    job["video_path"] = local_path or job.get("video_path") or ""
    job["video_url"] = public_url or job.get("video_url") or ""
    job["confirmations_after_approval"] = int(rule.get("confirmations_after_approval", 0) or 0)
    job["channels"] = _merge_channels(job.get("channels") or [], rule)
    job["rule_file"] = "Data/configs/buffer_product_posting.json"

    _attempt_send(job, rule, resolved_title, script, poster or graphql)

    data = load_queue()
    items = [row for row in data.get("items") or [] if row.get("id") != job.get("id")]
    items.append(job)
    data["items"] = items
    data["rule_file"] = "Data/configs/buffer_product_posting.json"
    _save_json(QUEUE_FILE, data)

    if item is not None:
        _stamp_catalog(catalog_file, catalog, item, job, public_url or local_path)

    job["ok"] = True
    job["scheduled"] = job.get("status") == "scheduled"
    return job


def flush_pending(poster: Poster | None = None) -> list[dict]:
    """Retry queued product cuts. Safe to run after a token or URL is added."""
    results = []
    for job in list(load_queue().get("items") or []):
        if job.get("status") == "scheduled":
            results.append(job)
            continue
        results.append(
            schedule_approved_product_cut(
                str(job.get("product_name") or ""),
                str(job.get("video_path") or ""),
                title=str(job.get("title") or "") or None,
                video_url=str(job.get("video_url") or "") or None,
                poster=poster,
            )
        )
    return results


def queue_brief() -> dict:
    """One line for `bolt queue` about the product-cut Buffer path."""
    rule = load_rule()
    labels = [
        str(ch.get("label") or ch.get("key") or "")
        for ch in (rule.get("channels") or [])
        if isinstance(ch, dict)
    ]
    items = load_queue().get("items") or []
    pending = [job for job in items if job.get("status") != "scheduled"]
    target = " + ".join(labels) if labels else "the channels in the rule file"
    line = (
        f"{len(items)} Buffer job(s), {len(pending)} not scheduled yet. "
        f"An approved product cut goes to {target} with no second confirmation. "
        f"`bolt buffer status`"
    )
    return {
        "count": len(items),
        "pending": len(pending),
        "line": line,
        "rule_file": "Data/configs/buffer_product_posting.json",
    }


def status_report() -> dict:
    rule = load_rule()
    token = access_token()
    items = load_queue().get("items") or []
    return {
        "ready": bool(rule) and bool(rule.get("enabled", True)),
        "auto_upload": bool(token),
        "rule_file": str(RULE_FILE),
        "queue_file": str(QUEUE_FILE),
        "trigger": rule.get("trigger"),
        "confirmations_after_approval": rule.get("confirmations_after_approval"),
        "via": rule.get("via"),
        "mode": rule.get("mode"),
        "scheduling_type": rule.get("scheduling_type"),
        "channels": [
            {
                "label": ch.get("label"),
                "service": ch.get("service"),
                "handle": ch.get("handle") or "",
                "display_name": ch.get("display_name") or "",
                "buffer_channel_id_set": bool(str(ch.get("buffer_channel_id") or "").strip()),
            }
            for ch in (rule.get("channels") or [])
            if isinstance(ch, dict)
        ],
        "credentials": "present" if token else "missing",
        "credential_env": "BUFFER_ACCESS_TOKEN",
        "job_count": len(items),
        "jobs": [
            {
                "id": job.get("id"),
                "product_name": job.get("product_name"),
                "status": job.get("status"),
                "detail": job.get("detail"),
                "channels": [
                    {
                        "label": ch.get("label"),
                        "status": ch.get("status"),
                        "buffer_post_id": ch.get("buffer_post_id") or "",
                    }
                    for ch in (job.get("channels") or [])
                ],
            }
            for job in items
        ],
        "hint": (
            "Product-cut approval schedules Buffer automatically when "
            "BUFFER_ACCESS_TOKEN, channel ids, and a public https video URL exist. "
            "Otherwise the queue file holds the job. Stream clips are unchanged."
        ),
    }


def _print_job(job: dict) -> None:
    print(f"  {job.get('product_name')}  [{job.get('status')}]  id={job.get('id')}")
    print(f"    {job.get('detail')}")
    for channel in job.get("channels") or []:
        post_id = channel.get("buffer_post_id") or ""
        extra = f"  post={post_id}" if post_id else ""
        print(f"    • {channel.get('label')}: {channel.get('status')}{extra}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description=(
            "Buffer schedule for an approved product cut. "
            "Rule: Data/configs/buffer_product_posting.json. "
            "No second confirmation after the cut is approved."
        )
    )
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="Show the locked rule and queued jobs")
    p_status.add_argument("--json", action="store_true")

    p_flush = sub.add_parser("flush", help="Retry queued jobs (after a token or URL is set)")
    p_flush.add_argument("--json", action="store_true")

    p_approve = sub.add_parser(
        "approve",
        help="Approve a finished product cut and schedule it on Buffer",
    )
    p_approve.add_argument("name")
    p_approve.add_argument("--video", default="")
    p_approve.add_argument("--video-url", default="")
    p_approve.add_argument("--title", default="")
    p_approve.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd is None:
        args.cmd = "status"
        args.json = False

    if args.cmd == "status":
        report = status_report()
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        print("Buffer product posting")
        print("─" * 40)
        print(f"  rule: {report.get('rule_file')}")
        print(
            f"  trigger={report.get('trigger')}  "
            f"confirmations_after_approval={report.get('confirmations_after_approval')}  "
            f"via={report.get('via')}"
        )
        print(
            f"  mode={report.get('mode')}  scheduling={report.get('scheduling_type')}  "
            f"credentials={report.get('credentials')}"
        )
        for channel in report.get("channels") or []:
            flag = "id set" if channel.get("buffer_channel_id_set") else "id blank"
            print(f"  • {channel.get('label')} ({flag})")
        print(f"  queue: {report.get('queue_file')}  jobs={report.get('job_count')}")
        print(f"  {report.get('hint')}")
        print()
        if not report.get("jobs"):
            print("  (no product cuts queued)")
            return 0
        for job in report["jobs"]:
            _print_job(job)
        return 0

    if args.cmd == "flush":
        jobs = flush_pending()
        if args.json:
            json.dump(jobs, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"flushed {len(jobs)} job(s)")
            for job in jobs:
                _print_job(job)
        return 0

    if args.cmd == "approve":
        job = schedule_approved_product_cut(
            args.name,
            args.video,
            title=args.title or None,
            video_url=args.video_url or None,
        )
        if args.json:
            json.dump(job, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            if job.get("ok"):
                print(f"Approved \"{args.name}\". No second confirmation.")
            _print_job(job) if job.get("channels") else print(f"  {job.get('detail')}")
            if not job.get("channels"):
                print(f"  status: {job.get('status')}")
        return 0 if job.get("ok") else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    import sys

    sys.exit(main())
