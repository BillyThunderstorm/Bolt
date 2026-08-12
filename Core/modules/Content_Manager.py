#!/usr/bin/env python3
"""
Content_Manager.py — Bolt as William's creator manager + business assistant
==========================================================================
Local-first system of record for:
  - game / tech / product / skincare testing
  - review drafts
  - Amazon storefront (affiliate tag billycarter-20)
  - social connectivity + approval-gated post plans
  - sponsor / affiliate prospects
  - business learning + Bolt advancement
  - "Good Morning Bolt" spoken briefing

CLI (via bolt or python -m modules.Content_Manager):
  manage add|list|note|draft|next|status
  store add|list|feature-next
  social status|package|queue
  sponsors find|pitch|log|next
  business lesson|next
  advance next
  morning [--speak|--quiet]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

# Repo root: Core/modules/thisfile -> parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "Data"
CONTENT_DIR = DATA_DIR / "content"
BUSINESS_DIR = DATA_DIR / "business"
DOCS_REVIEWS = REPO_ROOT / "Docs" / "reviews"
BRIEFINGS_DIR = REPO_ROOT / "Docs" / "briefings" / "daily"

CATALOG_FILE = CONTENT_DIR / "catalog.json"
STOREFRONT_FILE = CONTENT_DIR / "storefront.json"
SPONSORS_FILE = CONTENT_DIR / "sponsors.json"
SOCIAL_FILE = CONTENT_DIR / "social_connections.json"
REVIEW_TRACKER = DOCS_REVIEWS / "review_tracker.json"
BUSINESS_PLAYBOOK = BUSINESS_DIR / "business-playbook.md"
ADVANCEMENT_FILE = BUSINESS_DIR / "bolt-advancement.md"

# Creator prefs (William)
CREATOR_NAME = "William"
PREFERRED_LANES = ["game", "tech"]
AMAZON_TAG = "billycarter-20"
REQUIRE_POST_APPROVAL = True

LANES = ("game", "tech", "product", "skincare")
STATUSES = ("idea", "queued", "testing", "drafting", "ready", "posted", "shelved")

# Seed sponsor prospects (starter-friendly; local research list, not live scrape)
DEFAULT_SPONSORS: List[Dict[str, Any]] = [
    {
        "name": "Razer",
        "lanes": ["game", "tech"],
        "type": "brand+affiliate",
        "fit": 9,
        "why": "Core gaming peripherals; strong starter review products (mice, pads, headsets).",
        "affiliate_hint": "RazerStore affiliate / creator programs",
        "contact_hint": "creators@razer.com / brand portal",
    },
    {
        "name": "Logitech G",
        "lanes": ["game", "tech"],
        "type": "brand+affiliate",
        "fit": 9,
        "why": "Mice, keyboards, headsets — easy first reviews from gear William already uses.",
        "affiliate_hint": "Logitech affiliate / creator program",
        "contact_hint": "influencer marketing / press kit",
    },
    {
        "name": "SteelSeries",
        "lanes": ["game", "tech"],
        "type": "brand",
        "fit": 8,
        "why": "Headset and mouse reviews perform well for FPS/BR audiences.",
        "affiliate_hint": "SteelSeries affiliate",
        "contact_hint": "press@steelseries.com",
    },
    {
        "name": "HyperX",
        "lanes": ["game", "tech"],
        "type": "brand+affiliate",
        "fit": 8,
        "why": "Accessible price tiers; good for honest mid-range gear content.",
        "affiliate_hint": "HP/HyperX affiliate portals",
        "contact_hint": "creator outreach form",
    },
    {
        "name": "Elgato",
        "lanes": ["tech", "game"],
        "type": "brand",
        "fit": 8,
        "why": "Stream setup gear (lights, capture, mic arms) pairs with Twitch growth story.",
        "affiliate_hint": "Corsair/Elgato creator",
        "contact_hint": "creator@elgato.com",
    },
    {
        "name": "Secretlab",
        "lanes": ["tech", "game"],
        "type": "brand",
        "fit": 7,
        "why": "High AOV chair reviews; needs longer test journal.",
        "affiliate_hint": "Secretlab affiliate",
        "contact_hint": "influencers@secretlab.co",
    },
    {
        "name": "Amazon Influencer / Associates",
        "lanes": ["product", "tech", "game", "skincare"],
        "type": "affiliate",
        "fit": 10,
        "why": "William already has tag billycarter-20 — primary monetization path.",
        "affiliate_hint": f"tag={AMAZON_TAG}",
        "contact_hint": "associates / influencer dashboard",
    },
    {
        "name": "Anker / Soundcore",
        "lanes": ["tech", "product"],
        "type": "brand+affiliate",
        "fit": 7,
        "why": "Chargers, earbuds, power banks — constant short-form review fuel.",
        "affiliate_hint": "Anker affiliate",
        "contact_hint": "influencer@anker.com",
    },
    {
        "name": "CeraVe",
        "lanes": ["skincare"],
        "type": "brand",
        "fit": 6,
        "why": "Accessible skincare; good when beauty lane is active.",
        "affiliate_hint": "often via Amazon",
        "contact_hint": "L'Oréal / CeraVe PR",
    },
    {
        "name": "The Ordinary",
        "lanes": ["skincare"],
        "type": "brand",
        "fit": 6,
        "why": "Ingredient-led content pairs with honest testing journals.",
        "affiliate_hint": "Deciem affiliate when available",
        "contact_hint": "PR / creator form",
    },
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:48] or uuid4().hex[:8]


def _safe_load(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return default


def _safe_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _ensure_seed_files() -> None:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    BUSINESS_DIR.mkdir(parents=True, exist_ok=True)
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)

    if not CATALOG_FILE.exists():
        _safe_write(
            CATALOG_FILE,
            {
                "version": 1,
                "updated_at": _now_iso(),
                "preferred_lanes": PREFERRED_LANES,
                "items": [],
            },
        )

    if not STOREFRONT_FILE.exists():
        _safe_write(
            STOREFRONT_FILE,
            {
                "version": 1,
                "affiliate_tag": AMAZON_TAG,
                "storefront_status": "influencer_active",
                "updated_at": _now_iso(),
                "items": [],
            },
        )

    if not SPONSORS_FILE.exists():
        prospects = []
        for row in DEFAULT_SPONSORS:
            prospects.append(
                {
                    "id": _slug(row["name"]),
                    "name": row["name"],
                    "lanes": row["lanes"],
                    "type": row["type"],
                    "fit": row["fit"],
                    "why": row["why"],
                    "affiliate_hint": row["affiliate_hint"],
                    "contact_hint": row["contact_hint"],
                    "status": "prospect",
                    "outreach": [],
                    "added_at": _now_iso(),
                }
            )
        _safe_write(
            SPONSORS_FILE,
            {
                "version": 1,
                "updated_at": _now_iso(),
                "prospects": prospects,
            },
        )

    if not SOCIAL_FILE.exists():
        _safe_write(
            SOCIAL_FILE,
            {
                "version": 1,
                "require_approval": REQUIRE_POST_APPROVAL,
                "updated_at": _now_iso(),
                "platforms": {
                    "tiktok": {
                        "handle": "@itssimplybilly",
                        "status": "configured",
                        "upload_mode": "api_when_token",
                        "notes": "Primary short-form. Use Content Posting API when token present.",
                    },
                    "twitch": {
                        "handle": "ItsSimplyBilly",
                        "status": "configured",
                        "upload_mode": "live_source",
                        "notes": "Live gameplay + highlight source. Aligned with SimplyBilly brand.",
                    },
                    "youtube": {
                        "handle": "@SimplyBilly",
                        "status": "configured",
                        "upload_mode": "manual_assisted",
                        "notes": "Long-form reviews + Shorts. API needs OAuth app approval.",
                    },
                    "x": {
                        "handle": "@SimplyBilly_",
                        "status": "configured",
                        "upload_mode": "manual_assisted",
                        "notes": "Quick takes and reposts.",
                    },
                    "instagram": {
                        "handle": "TBD",
                        "status": "not_connected",
                        "upload_mode": "manual_assisted",
                        "notes": "Optional Reels later.",
                    },
                },
                "queue": [],
            },
        )

    if not BUSINESS_PLAYBOOK.exists():
        BUSINESS_PLAYBOOK.write_text(
            """# Creator Business Playbook (William + Bolt)

## North Star
Become a trusted voice for **games and tech testing**, with product/skincare lanes as expansion.
Monetize via Amazon Influencer (`billycarter-20`), affiliates, then brand deals.

## Stage Map
1. **Proof** — post consistent honest reviews/clips (games + tech first)
2. **Portfolio** — 5+ public reviews + media kit
3. **Affiliate** — every review has a tracked link when relevant
4. **Outreach** — pitch 5 brands/week with templates
5. **Deals** — negotiate gifting → paid once metrics exist
6. **Systems** — Bolt automates research, drafts, queue, follow-ups

## Weekly Rhythm (starter)
- Mon: pick 1 game or tech item to test / film
- Tue: journal notes + short-form cut
- Wed: post + engage comments
- Thu: long-form or stream segment
- Fri: pitch 5 brands / check affiliate dashboard
- Sat: stream (Twitch) + clip harvest
- Sun: review numbers + plan next week with Bolt

## Disclosures
- Always disclose gifted/sponsored content (#ad / #gifted)
- Affiliate links need honest opinion first; never fake results

## First Money Paths
1. Amazon Associates / Influencer with tag `billycarter-20`
2. Platform creator funds (TikTok Creativity, YT Partner later)
3. Affiliate programs (peripheral brands)
4. Sponsored reviews after portfolio exists

## Advancement Rule
Ship content before perfect systems. Bolt upgrades should reduce friction on posting and testing.
""",
            encoding="utf-8",
        )

    if not ADVANCEMENT_FILE.exists():
        ADVANCEMENT_FILE.write_text(
            """# Bolt Advancement Roadmap

Priority order for making Bolt a better manager:

1. Content Manager catalog + journals (done when this ships)
2. Good Morning Bolt spoken briefing
3. Amazon storefront linking on every review draft
4. Social package planner with approval gate
5. Sponsor prospector + pitch drafts
6. Real YouTube/X OAuth upload when apps approved
7. Stream companion intents (manage/next during voice chat)
8. Performance feedback loop into next-content suggestions

## How William advances Bolt
- After each content session, tell Bolt what felt slow
- Prefer local tools over paid APIs when possible
- One upgrade at a time; finish > start
""",
            encoding="utf-8",
        )


def load_catalog() -> Dict[str, Any]:
    _ensure_seed_files()
    return _safe_load(CATALOG_FILE, {"items": []})


def save_catalog(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    _safe_write(CATALOG_FILE, data)


def load_storefront() -> Dict[str, Any]:
    _ensure_seed_files()
    return _safe_load(STOREFRONT_FILE, {"items": [], "affiliate_tag": AMAZON_TAG})


def save_storefront(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    data["affiliate_tag"] = data.get("affiliate_tag") or AMAZON_TAG
    _safe_write(STOREFRONT_FILE, data)


def load_review_tracker() -> Dict[str, Any]:
    _ensure_seed_files()
    return _safe_load(REVIEW_TRACKER, {"reviews": [], "outreach_log": [], "products_received": [], "settings": {}})


def save_review_tracker(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    _safe_write(REVIEW_TRACKER, data)


# ---------------------------------------------------------------------------
# TikTok publishing bridge
#
# M11 is "TikTok API token end-to-end publish (still approval-gated)".
# The code to do the publish already lives in `modules/TikTok_Publisher.py`.
# What's missing is the bridge from the catalog (a `ready` item with a
# draft) to the publisher, plus a status report so the operator can tell
# what's blocking a real publish (missing creds, expired token, missing
# video.publish scope, etc.).
# ---------------------------------------------------------------------------


def tiktok_publish_status() -> Dict[str, Any]:
    """Report what's blocking a real TikTok publish.

    The four things that need to be true for `bolt manage post` to
    actually upload:

      1. .env has TIKTOK_CLIENT_KEY
      2. .env has TIKTOK_CLIENT_SECRET
      3. .env has a non-placeholder TIKTOK_ACCESS_TOKEN
      4. The token's scope includes video.publish (best-effort check
         based on TIKTOK_SCOPE; TikTok ultimately decides what the
         app is approved for)
    """
    status: Dict[str, Any] = {
        "ready": False,
        "checks": [],
        "next_steps": [],
    }
    try:
        from modules import TikTok_Auth as auth

        env = auth.load_env()
    except Exception as exc:  # pragma: no cover - defensive
        status["checks"].append({"name": "load_env", "ok": False, "detail": str(exc)})
        return status

    has_key = bool(env.get("TIKTOK_CLIENT_KEY"))
    has_secret = bool(env.get("TIKTOK_CLIENT_SECRET")) and not env.get(
        "TIKTOK_CLIENT_SECRET", ""
    ).startswith("TIKTOK_")
    token = env.get("TIKTOK_ACCESS_TOKEN", "")
    has_token = bool(token) and not token.startswith("TIKTOK_")
    scope = env.get("TIKTOK_SCOPE", "")
    has_publish_scope = "video.publish" in scope

    status["checks"].extend([
        {"name": "TIKTOK_CLIENT_KEY", "ok": has_key,
         "detail": "set" if has_key else "missing or placeholder"},
        {"name": "TIKTOK_CLIENT_SECRET", "ok": has_secret,
         "detail": "set" if has_secret else "missing or placeholder"},
        {"name": "TIKTOK_ACCESS_TOKEN", "ok": has_token,
         "detail": "set" if has_token else "missing or placeholder"},
        {"name": "scope includes video.publish", "ok": has_publish_scope,
         "detail": scope or "(no TIKTOK_SCOPE set)"},
    ])

    if not has_key:
        status["next_steps"].append("Set TIKTOK_CLIENT_KEY in .env (TikTok developer portal).")
    if not has_secret:
        status["next_steps"].append("Set TIKTOK_CLIENT_SECRET in .env.")
    if not has_token:
        status["next_steps"].append(
            "Run `bolt tiktok_token` to do the OAuth flow and write tokens to .env."
        )
    if not has_publish_scope and has_token:
        status["next_steps"].append(
            "Re-run the OAuth flow requesting video.publish scope. "
            "If TikTok has not approved your app for that scope yet, "
            "M11 stays blocked at TikTok's side."
        )

    status["ready"] = has_key and has_secret and has_token
    return status


def tiktok_publish_dry_run(name: str) -> Dict[str, Any]:
    """Show what a real `bolt manage post` would do without touching
    the network. Returns the resolved video path, the title and
    hashtag set that would be sent, and the publisher status.
    """
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")
    if not item.get("last_draft"):
        raise ValueError(
            f"'{item['name']}' has no draft. Run "
            f"`bolt manage draft \"{item['name']}\"` first."
        )
    if item.get("status") == "posted":
        raise ValueError(f"'{item['name']}' is already posted.")

    # Find a video for this item. Convention: media/clips/<id>.mp4
    # or media/vertical_clips/<id>.mp4. Fall back to the most recent
    # clip in either directory if no exact match.
    repo = REPO_ROOT
    candidates = []
    item_id = item.get("id", _slug(item["name"]))
    for clips_dir in (repo / "media" / "clips", repo / "media" / "vertical_clips"):
        for ext in (".mp4", ".mov", ".mkv"):
            candidate = clips_dir / f"{item_id}{ext}"
            if candidate.exists():
                candidates.append(candidate)
    resolved_video = str(candidates[0]) if candidates else None

    draft = item.get("last_draft", {})
    title = f"{item['name']} — honest take"
    hashtags = ["#gaming", "#tech"] if item.get("lane") == "tech" else ["#gaming"]

    return {
        "name": item["name"],
        "status": item.get("status"),
        "video_path": resolved_video,
        "video_found": bool(resolved_video),
        "title": title,
        "hashtags": hashtags,
        "affiliate_link": draft.get("affiliate_link"),
        "publisher_status": tiktok_publish_status(),
    }


def tiktok_publish_item(
    name: str,
    approve: bool = False,
    video_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Actually publish a `ready` or `drafting` catalog item to TikTok.

    Refuses unless `approve=True` is passed (REQUIRE_POST_APPROVAL).
    On success, advances the catalog to 'posted' via mark_posted and
    records the platform + post URL.

    Returns a dict with success/error, the post URL if successful, and
    the mark_posted result.
    """
    if not approve:
        raise PermissionError(
            "Refusing to post without --approve. Approval-gated by "
            "REQUIRE_POST_APPROVAL in your Content Manager settings."
        )

    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")
    if item.get("status") not in ("ready", "drafting"):
        raise ValueError(
            f"'{item['name']}' is status='{item.get('status')}'. "
            f"Mark it ready first with `bolt manage mark-ready \"{item['name']}\"`."
        )
    if not item.get("last_draft"):
        raise ValueError(
            f"'{item['name']}' has no draft. Run `bolt manage draft \"{item['name']}\"`."
        )

    pub_status = tiktok_publish_status()
    if not pub_status["ready"]:
        return {
            "success": False,
            "error": "publisher_not_ready",
            "publisher_status": pub_status,
            "next_steps": pub_status["next_steps"],
        }

    # Resolve the video path: explicit override, or the dry-run's pick.
    if not video_path:
        preview = tiktok_publish_dry_run(name)
        video_path = preview["video_path"]
    if not video_path or not Path(video_path).exists():
        return {
            "success": False,
            "error": "video_not_found",
            "video_path": video_path,
            "hint": (
                "Drop the clip in media/clips/<item_id>.mp4 or pass "
                "--video /path/to/clip.mp4"
            ),
        }

    try:
        from modules import TikTok_Publisher as tp
    except Exception as exc:  # pragma: no cover - import error
        return {"success": False, "error": f"import_failed: {exc}"}

    draft = item.get("last_draft", {})
    title = f"{item['name']} — honest take"
    hashtags = ["#gaming", "#tech"] if item.get("lane") == "tech" else ["#gaming"]

    result = tp.publish_clip(video_path, title, hashtags=hashtags)
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "publish_failed"),
            "publish_id": result.get("publish_id"),
        }

    # Auto-advance the catalog to 'posted' with the platform + URL.
    post_record = mark_posted(
        name,
        platforms=["tiktok"],
        where=result.get("url") or result.get("publish_id", ""),
        note="auto-recorded by bolt manage post",
    )
    return {
        "success": True,
        "url": result.get("url"),
        "publish_id": result.get("publish_id"),
        "post_record": post_record,
    }


def mark_ready(name: str, verdict: str = "", note: str = "") -> Dict[str, Any]:
    """Move a catalog item from 'drafting' to 'ready' (review is done,
    draft is approved, ready to be posted).

    Refuses to mark items as ready that have no draft. Records the
    transition so it's visible in the catalog history.
    """
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")
    if not item.get("last_draft"):
        raise ValueError(
            f"'{item['name']}' has no draft yet. Run "
            f"`bolt manage draft \"{item['name']}\"` first."
        )
    if item.get("status") == "posted":
        raise ValueError(f"'{item['name']}' is already posted.")
    item["status"] = "ready"
    if verdict:
        item["verdict"] = verdict
    if note:
        item.setdefault("notes_log", []).append(
            {"day": None, "text": f"Ready: {note}", "at": _now_iso()}
        )
    item["marked_ready_at"] = _now_iso()
    save_catalog(catalog)
    return item


def mark_posted(
    name: str,
    platforms: Optional[List[str]] = None,
    where: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """Record that a 'ready' item was actually posted. Appends an entry
    to review_tracker.json so the shipped review is auditable, and
    flips the catalog status to 'posted'.

    `platforms` is a list like ['tiktok', 'youtube_shorts']. `where`
    is a free-text field for the post URL or video ID.

    If the item is *already* posted, this merges any new platforms /
    where / note instead of erroring — common when logging Amazon after
    social, or fixing a typo on a second pass.
    """
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")

    platforms = list(platforms or [])
    status = item.get("status")

    # Soft update when already shipped
    if status == "posted":
        existing = list(item.get("posted_platforms") or [])
        merged = list(dict.fromkeys(existing + platforms))  # preserve order, dedupe
        item["posted_platforms"] = merged
        if where:
            item["posted_where"] = where
        if note:
            item.setdefault("notes_log", []).append(
                {"day": None, "text": f"Post update: {note}", "at": _now_iso()}
            )
        if platforms or where or note:
            tracker = load_review_tracker()
            update_entry = {
                "id": _slug(f"{item['name']}-update-{_now_iso()}"),
                "item_id": item.get("id"),
                "name": item["name"],
                "lane": item.get("lane", "tech"),
                "platforms": platforms or merged,
                "where": where or item.get("posted_where", ""),
                "note": note or "platforms updated",
                "posted_at": _now_iso(),
                "posted_by": CREATOR_NAME,
                "kind": "update",
            }
            tracker.setdefault("reviews", []).append(update_entry)
            save_review_tracker(tracker)
            save_catalog(catalog)
            return {
                "catalog_item": item,
                "review_entry": update_entry,
                "updated": True,
                "platforms": merged,
            }
        raise ValueError(
            f"'{item['name']}' is already posted "
            f"({', '.join(existing) or 'no platforms logged'}). "
            f"Add platforms with e.g. "
            f"`bolt manage posted \"{item['name']}\" --amazon` "
            f"or `--platforms amazon --where <url>`."
        )

    if status not in ("ready", "drafting"):
        raise ValueError(
            f"'{item['name']}' is status='{status}'. "
            f"Mark it ready first with `bolt manage ready \"{item['name']}\"` "
            f"(alias for mark-ready)."
        )

    draft = item.get("last_draft") or {}
    review_entry = {
        "id": _slug(f"{item['name']}-{_now_iso()}"),
        "item_id": item.get("id"),
        "name": item["name"],
        "lane": item.get("lane", "tech"),
        "format": draft.get("format", "short"),
        "platforms": platforms,
        "where": where,
        "verdict": item.get("verdict"),
        "affiliate_link": item.get("last_draft", {}).get("affiliate_link"),
        "script": draft.get("script", ""),
        "note": note,
        "posted_at": _now_iso(),
        "posted_by": CREATOR_NAME,
    }
    tracker = load_review_tracker()
    tracker.setdefault("reviews", []).append(review_entry)
    save_review_tracker(tracker)

    item["status"] = "posted"
    item["posted_at"] = _now_iso()
    item["posted_platforms"] = platforms
    item["posted_where"] = where
    save_catalog(catalog)
    return {
        "catalog_item": item,
        "review_entry": review_entry,
        "updated": False,
        "platforms": platforms,
    }


def shipped_reviews(limit: int = 50) -> List[Dict[str, Any]]:
    """Return shipped review entries from review_tracker, newest first."""
    tracker = load_review_tracker()
    reviews = tracker.get("reviews", [])
    return list(reversed(reviews[-limit:]))


def shipped_summary() -> Dict[str, Any]:
    """Compact summary for `manage status` and morning briefing."""
    reviews = shipped_reviews(limit=1000)
    by_lane: Dict[str, int] = {}
    for r in reviews:
        lane = r.get("lane", "unknown")
        by_lane[lane] = by_lane.get(lane, 0) + 1
    return {
        "total": len(reviews),
        "by_lane": by_lane,
        "last_posted_at": reviews[0]["posted_at"] if reviews else None,
    }


def load_sponsors() -> Dict[str, Any]:
    _ensure_seed_files()
    return _safe_load(SPONSORS_FILE, {"prospects": []})


def save_sponsors(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    _safe_write(SPONSORS_FILE, data)


def load_social() -> Dict[str, Any]:
    _ensure_seed_files()
    return _safe_load(SOCIAL_FILE, {"platforms": {}, "queue": []})


def save_social(data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    data["require_approval"] = REQUIRE_POST_APPROVAL
    _safe_write(SOCIAL_FILE, data)


def _find_item(catalog: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    key = name.strip().lower()
    for item in catalog.get("items", []):
        if item.get("name", "").lower() == key or item.get("id") == key:
            return item
        if key in item.get("name", "").lower():
            return item
    return None


def add_item(
    name: str,
    lane: str = "tech",
    status: str = "testing",
    notes: str = "",
    asin: str = "",
) -> Dict[str, Any]:
    lane = lane.lower().strip()
    if lane not in LANES:
        raise ValueError(f"lane must be one of {LANES}")
    status = status.lower().strip()
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")

    catalog = load_catalog()
    existing = _find_item(catalog, name)
    if existing:
        existing["status"] = status
        existing["lane"] = lane
        if notes:
            existing.setdefault("notes_log", []).append(
                {"day": None, "text": notes, "at": _now_iso()}
            )
        if asin:
            existing["asin"] = asin
        save_catalog(catalog)
        return existing

    item = {
        "id": _slug(name),
        "name": name.strip(),
        "lane": lane,
        "status": status,
        "asin": asin or "",
        "started_at": _today(),
        "created_at": _now_iso(),
        "notes_log": [],
        "verdict": None,
        "priority": 10 if lane in PREFERRED_LANES else 5,
    }
    if notes:
        item["notes_log"].append({"day": 1, "text": notes, "at": _now_iso()})
    catalog.setdefault("items", []).append(item)
    save_catalog(catalog)

    # Sync lightweight review tracker
    tracker = _safe_load(
        REVIEW_TRACKER,
        {"reviews": [], "outreach_log": [], "products_received": [], "settings": {}},
    )
    tracker.setdefault("products_received", []).append(
        {
            "name": item["name"],
            "lane": lane,
            "status": status,
            "asin": asin,
            "added_at": _now_iso(),
        }
    )
    _safe_write(REVIEW_TRACKER, tracker)
    return item


def list_items(lane: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    items = load_catalog().get("items", [])
    if lane:
        items = [i for i in items if i.get("lane") == lane.lower()]
    if status:
        items = [i for i in items if i.get("status") == status.lower()]
    # preferred lanes first, then testing
    def sort_key(i: Dict[str, Any]):
        pref = 0 if i.get("lane") in PREFERRED_LANES else 1
        st = 0 if i.get("status") == "testing" else 1
        return (pref, st, i.get("name", ""))

    return sorted(items, key=sort_key)


def add_note(name: str, text: str, day: Optional[int] = None) -> Dict[str, Any]:
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'. Add it first.")
    entry = {"day": day, "text": text.strip(), "at": _now_iso()}
    item.setdefault("notes_log", []).append(entry)
    if item.get("status") == "idea":
        item["status"] = "testing"
    save_catalog(catalog)
    return item


def build_draft(name: str, format: str = "short") -> Dict[str, Any]:
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")

    notes = item.get("notes_log") or []
    note_text = " | ".join(n.get("text", "") for n in notes[-5:]) or "Still gathering real-world notes."
    lane = item.get("lane", "tech")
    store = load_storefront()
    tag = store.get("affiliate_tag", AMAZON_TAG)
    asin = item.get("asin") or ""
    affiliate = (
        f"https://www.amazon.com/dp/{asin}/?tag={tag}" if asin else f"(add ASIN; tag={tag})"
    )

    shape = {
        "what_it_is": f"{item['name']} ({lane})",
        "why_tested": "Real-world game/tech testing for honest creator reviews.",
        "first_impression": notes[0]["text"] if notes else "Not logged yet.",
        "what_worked": note_text,
        "what_got_in_the_way": "Call out friction honestly when logged.",
        "who_it_is_for": "Gamers and tech buyers who want practical takes, not hype.",
        "verdict": item.get("verdict") or "Pending — keep testing until a clear call.",
    }

    if format == "short":
        script = (
            f"Hook: I've been testing the {item['name']} — honest take.\n"
            f"What it is: {shape['what_it_is']}\n"
            f"Demo notes: {shape['what_worked']}\n"
            f"Who it's for: {shape['who_it_is_for']}\n"
            f"Verdict: {shape['verdict']}\n"
            f"Affiliate: {affiliate}\n"
            f"Disclosure: honest opinion; links may earn commission."
        )
    else:
        script = (
            f"1. Intro/hook — {item['name']}\n"
            f"2. What it is — {shape['what_it_is']}\n"
            f"3. Why William tested it — {shape['why_tested']}\n"
            f"4. First impression — {shape['first_impression']}\n"
            f"5. What worked — {shape['what_worked']}\n"
            f"6. What got in the way — {shape['what_got_in_the_way']}\n"
            f"7. Who it's for — {shape['who_it_is_for']}\n"
            f"8. Verdict — {shape['verdict']}\n"
            f"9. Link — {affiliate}\n"
        )

    draft = {
        "item_id": item["id"],
        "name": item["name"],
        "lane": lane,
        "format": format,
        "shape": shape,
        "script": script,
        "affiliate_link": affiliate,
        "platforms": ["tiktok", "youtube_shorts", "x"] if format == "short" else ["youtube", "twitch"],
        "created_at": _now_iso(),
    }
    item["last_draft"] = draft
    item["status"] = "drafting" if item.get("status") in ("testing", "idea", "queued") else item.get("status")
    save_catalog(catalog)
    return draft


def next_actions(limit: int = 3) -> List[Dict[str, str]]:
    """One clear stack: content, business, bolt advance — preferred lanes first."""
    actions: List[Dict[str, str]] = []
    items = list_items()

    # Content: testing with few notes
    for item in items:
        if item.get("status") in ("testing", "queued", "idea") and item.get("lane") in PREFERRED_LANES:
            n = len(item.get("notes_log") or [])
            if n == 0:
                actions.append(
                    {
                        "type": "content",
                        "title": f"Log day-1 notes for {item['name']}",
                        "why": "No journal yet — reviews need real observations.",
                        "command": f'bolt manage note "{item["name"]}" --day 1 --text "..."',
                    }
                )
                break
            if item.get("status") == "testing" and n >= 2 and not item.get("last_draft"):
                actions.append(
                    {
                        "type": "content",
                        "title": f"Draft short review for {item['name']}",
                        "why": "Enough notes to ship a short-form take.",
                        "command": f'bolt manage draft "{item["name"]}" --format short',
                    }
                )
                break

    if not any(a["type"] == "content" for a in actions):
        if not items:
            actions.append(
                {
                    "type": "content",
                    "title": "Add first game or tech item to the catalog",
                    "why": "Preferred lanes are games and tech — start with gear you already own.",
                    "command": 'bolt manage add "Your headset" --lane tech --status testing',
                }
            )
        else:
            top = items[0]
            actions.append(
                {
                    "type": "content",
                    "title": f"Move {top['name']} forward ({top.get('status')})",
                    "why": "Keep one item shipping instead of starting five.",
                    "command": f'bolt manage draft "{top["name"]}" --format short',
                }
            )

    # Business
    sponsors = load_sponsors().get("prospects", [])
    untouched = [s for s in sponsors if s.get("status") == "prospect"]
    if untouched:
        s = sorted(untouched, key=lambda x: -int(x.get("fit", 0)))[0]
        actions.append(
            {
                "type": "business",
                "title": f"Pitch or research {s['name']}",
                "why": s.get("why", "Strong fit for game/tech lane."),
                "command": f'bolt sponsors pitch "{s["name"]}"',
            }
        )
    else:
        actions.append(
            {
                "type": "business",
                "title": "Log affiliate dashboard check",
                "why": "Tag billycarter-20 should be on active review links.",
                "command": "bolt business lesson",
            }
        )

    # Bolt advance
    actions.append(
        {
            "type": "advance",
            "title": "Ship one content action before the next Bolt feature",
            "why": "Content proof advances the business faster than idle tooling.",
            "command": "bolt advance next",
        }
    )
    return actions[:limit]


def store_add(name: str, asin: str = "", category: str = "tech", notes: str = "",
              verify: bool = False) -> Dict[str, Any]:
    """Add or update a storefront item.

    If `verify` is True, calls `Amazon_Analyzer.fetch_product_details(asin)`
    to confirm the ASIN resolves to a real Amazon product before saving.
    On any network/HTTP error or missing product data, the item is still
    saved but `verify_error` is recorded on the item so the operator
    can fix the ASIN later.
    """
    data = load_storefront()
    asin = asin.strip().upper()
    tag = data.get("affiliate_tag", AMAZON_TAG)
    link = f"https://www.amazon.com/dp/{asin}/?tag={tag}" if asin else ""
    item: Dict[str, Any] = {
        "id": _slug(name),
        "name": name.strip(),
        "asin": asin,
        "category": category,
        "affiliate_link": link,
        "status": "active",
        "notes": notes,
        "added_at": _now_iso(),
    }

    # Optional: verify the ASIN resolves to a real product. Network failures
    # are recorded but never block the add.
    if verify and asin:
        item["verify_status"] = "pending"
        try:
            from modules.Amazon_Analyzer import fetch_product_details
            details = fetch_product_details(asin)
            title = details.get("title") if isinstance(details, dict) else None
            if title and "Unknown" not in str(title):
                item["verified_title"] = title
                item["verify_status"] = "ok"
            else:
                item["verify_status"] = "no_match"
                item["verify_error"] = "Amazon did not return a product title for this ASIN"
        except Exception as exc:  # network / import / parse
            item["verify_status"] = "error"
            item["verify_error"] = f"{type(exc).__name__}: {exc}"

    # de-dupe by asin or name
    items = data.setdefault("items", [])
    for existing in items:
        if (asin and existing.get("asin") == asin) or existing.get("name", "").lower() == name.lower():
            existing.update({k: v for k, v in item.items() if v})
            save_storefront(data)
            return existing
    items.append(item)
    save_storefront(data)
    # also ensure catalog entry
    try:
        add_item(name=name, lane="tech" if category in ("tech", "game") else "product", asin=asin, notes=notes)
    except Exception:
        pass
    return item


def store_list() -> List[Dict[str, Any]]:
    return load_storefront().get("items", [])


def store_missing_asins() -> List[Dict[str, Any]]:
    """Return storefront items that have no ASIN. These are the items
    blocking M9 (real ASINs on owned gear) and the items that should
    be featured first once an ASIN is attached."""
    return [i for i in store_list() if not (i.get("asin") or "").strip()]


def store_summary() -> Dict[str, Any]:
    """Compact summary for `manage status` and the morning briefing."""
    items = store_list()
    with_asin = [i for i in items if (i.get("asin") or "").strip()]
    without_asin = [i for i in items if not (i.get("asin") or "").strip()]
    return {
        "total": len(items),
        "with_asin": len(with_asin),
        "missing_asin": len(without_asin),
        "missing_asin_names": [i.get("name", "?") for i in without_asin],
    }


def store_feature_next() -> Dict[str, Any]:
    items = store_list()
    if not items:
        return {
            "message": "Storefront is empty. Add an ASIN from gear you already use.",
            "command": 'bolt store add --name "Logitech mouse" --asin B0XXXX --category tech',
        }
    # Prefer items not yet drafted in catalog
    catalog = {i.get("asin"): i for i in load_catalog().get("items", []) if i.get("asin")}
    for s in items:
        cat = catalog.get(s.get("asin"))
        if not cat or not cat.get("last_draft"):
            return {
                "feature": s,
                "message": f"Feature {s['name']} next — build a short review with affiliate link.",
                "command": f'bolt manage draft "{s["name"]}" --format short',
            }
    s = items[0]
    return {
        "feature": s,
        "message": f"All storefront items have drafts. Revisit {s['name']} with a comparison angle.",
        "command": f'bolt manage note "{s["name"]}" --text "comparison angle"',
    }


def social_status() -> Dict[str, Any]:
    return load_social()


# ---------------------------------------------------------------------------
# Per-platform manual-assist package generators (M12)
#
# YouTube and X are flagged as `upload_mode: "manual_assisted"` in
# social_connections.json because real OAuth app review is still
# pending. Until that's granted, the best we can do is generate the
# exact text to paste into the upload UI on each platform, in the
# format that platform expects (title length, description, tags,
# disclosure). That gives the operator a one-command prep step and
# keeps the M10 audit trail intact (mark_posted after upload).
# ---------------------------------------------------------------------------


def _platform_settings() -> Dict[str, Any]:
    """Return the per-platform rules for title/description lengths,
    tag style, and disclosure language. These come from the platforms'
    own docs; if you need to tune them, edit here."""
    return {
        "youtube": {
            "title_max": 100,
            "description_max": 5000,
            "tag_max": 30,  # per-tag char limit
            "max_tags": 15,
            "disclosure": (
                "Includes affiliate links. As an Amazon Associate I earn from "
                "qualifying purchases. Honest opinion only."
            ),
            "default_tags": ["gaming", "tech review", "honest review"],
        },
        "x": {
            "title_max": 280,  # X post character limit
            "description_max": 280,
            "tag_max": 0,  # X doesn't use tags, uses @mentions + hashtags in body
            "max_tags": 3,
            "disclosure": "(affiliate link; honest opinion)",
            "default_tags": [],
        },
    }


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def build_youtube_package(name: str) -> Dict[str, Any]:
    """Build a YouTube-ready upload package for a catalog item:
    title, description (with timestamps, links, disclosure), tags,
    affiliate link. Designed to be pasted into the YouTube upload UI."""
    settings = _platform_settings()["youtube"]
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")
    if not item.get("last_draft"):
        raise ValueError(
            f"'{item['name']}' has no draft. Run `bolt manage draft \"{item['name']}\"` first."
        )

    draft = item["last_draft"]
    shape = draft.get("shape", {})
    asin = item.get("asin", "")
    affiliate = draft.get("affiliate_link", "")

    # Title: short and search-friendly
    base_title = f"{item['name']} — honest review"
    title = _truncate(base_title, settings["title_max"])

    # Description: hook, what it is, what worked, what didn't, who it's for,
    # verdict, link, disclosure. Each on its own line for readability.
    desc_lines = [
        shape.get("first_impression", "First impression notes from real use."),
        "",
        "What worked:",
        shape.get("what_worked", "Notes from the test journal."),
        "",
        "What got in the way:",
        shape.get("what_got_in_the_way", "Honest friction points from the test."),
        "",
        "Who it's for:",
        shape.get("who_it_is_for", "Practical buyers, not hype-chasers."),
        "",
        f"Verdict: {shape.get('verdict', 'Pending.')}",
        "",
    ]
    if affiliate and not affiliate.startswith("("):
        desc_lines.append(f"Buy it: {affiliate}")
    else:
        desc_lines.append("Buy it: (add ASIN to the catalog item for an Amazon link)")
    desc_lines.extend([
        "",
        settings["disclosure"],
        "",
        f"#shorts  #review  #{item.get('lane', 'tech')}  #honest",
    ])
    description = _truncate("\n".join(desc_lines), settings["description_max"])

    # Tags: include the item name words, the lane, the default tags,
    # and a sanitized form of the verdict.
    raw_tags = list(settings["default_tags"])
    raw_tags.append(item.get("lane", "tech"))
    raw_tags.append(item["name"].lower().replace(" ", "-")[: settings["tag_max"]])
    verdict_word = (shape.get("verdict") or "").split()[0:1]
    if verdict_word:
        raw_tags.append(verdict_word[0].lower())
    tags = []
    seen = set()
    for t in raw_tags:
        t = t.strip().lstrip("#")
        if not t or t in seen:
            continue
        seen.add(t)
        tags.append(_truncate(t, settings["tag_max"]))
        if len(tags) >= settings["max_tags"]:
            break

    return {
        "platform": "youtube",
        "platform_status": "manual_assisted",
        "handle": "TBD",  # filled in by caller if needed
        "title": title,
        "description": description,
        "tags": tags,
        "affiliate_link": affiliate,
        "category_suggestion": (
            "Science & Technology" if item.get("lane") == "tech" else "Gaming"
        ),
        "upload_url": "https://studio.youtube.com/channel/upload",
        "next_step": (
            "Paste the title, description, and tags into the YouTube upload UI. "
            "After the video is live, run: bolt manage mark-posted \"{name}\" "
            "--platforms youtube_shorts --where <video_url>".format(name=item["name"])
        ),
    }


def build_x_package(name: str) -> Dict[str, Any]:
    """Build an X (Twitter)-ready post for a catalog item. Short by
    design (280 chars), uses a single hashtag, points at the
    long-form content (TikTok/YouTube) via the catalog item's last
    draft."""
    settings = _platform_settings()["x"]
    catalog = load_catalog()
    item = _find_item(catalog, name)
    if not item:
        raise ValueError(f"No catalog item matching '{name}'.")
    if not item.get("last_draft"):
        raise ValueError(
            f"'{item['name']}' has no draft. Run `bolt manage draft \"{item['name']}\"` first."
        )

    draft = item["last_draft"]
    shape = draft.get("shape", {})
    verdict = (shape.get("verdict") or "Honest take").split(".")[0]
    body = f"{item['name']}: {verdict}. {settings['disclosure']}"
    post_text = _truncate(body, settings["title_max"])
    hashtags = [f"#{item.get('lane', 'gaming')}"]

    return {
        "platform": "x",
        "platform_status": "manual_assisted",
        "handle": "TBD",
        "post_text": post_text,
        "hashtags": hashtags[: settings["max_tags"]],
        "affiliate_link": draft.get("affiliate_link", ""),
        "upload_url": "https://x.com/compose/post",
        "next_step": (
            "Paste post_text + hashtags into the X compose UI. "
            "If the review has a video, attach it from your phone/desktop "
            "X client after the text is composed. After it's posted, run: "
            f"bolt manage mark-posted \"{item['name']}\" --platforms x "
            "--where <post_url>"
        ),
    }


def youtube_readiness() -> Dict[str, Any]:
    """What M12 needs to switch from manual_assisted to real API
    upload. Right now YouTube is always 'manual' because the OAuth
    app review hasn't been done. This helper reports the gap and
    lists the next steps."""
    return {
        "ready": False,  # always — until we build a real YouTube publisher
        "checks": [
            {
                "name": "YouTube Data API v3 OAuth app",
                "ok": False,
                "detail": (
                    "Not yet implemented. Until then, `bolt manage youtube-pkg` "
                    "generates a paste-ready upload package."
                ),
            },
            {
                "name": "manual upload package generator",
                "ok": True,
                "detail": "Available now as `bolt manage youtube-pkg NAME`.",
            },
        ],
        "next_steps": [
            "Use `bolt manage youtube-pkg \"ITEM\"` to generate the title, "
            "description, and tags to paste into the YouTube upload UI.",
            "After the upload is live, run `bolt manage mark-posted \"ITEM\" "
            "--platforms youtube_shorts --where <video_url>` to record it.",
            "If/when you want a real API publisher: create a Google Cloud "
            "project, enable YouTube Data API v3, set up OAuth consent screen, "
            "get client_id/secret into .env, then build Core/modules/YouTube_Publisher.py "
            "modeled on modules/TikTok_Publisher.py.",
        ],
    }


def x_readiness() -> Dict[str, Any]:
    """Same shape as youtube_readiness, for X."""
    return {
        "ready": False,
        "checks": [
            {
                "name": "X API v2 OAuth app",
                "ok": False,
                "detail": (
                    "Not yet implemented. Until then, `bolt manage x-pkg` "
                    "generates a paste-ready post body."
                ),
            },
            {
                "name": "manual post package generator",
                "ok": True,
                "detail": "Available now as `bolt manage x-pkg NAME`.",
            },
        ],
        "next_steps": [
            "Use `bolt manage x-pkg \"ITEM\"` to generate the 280-char post body.",
            "After the post is live, run `bolt manage mark-posted \"ITEM\" "
            "--platforms x --where <post_url>` to record it.",
            "For real API upload later: get an X developer app, set "
            "X_API_KEY/X_API_SECRET/X_BEARER_TOKEN in .env, and build "
            "Core/modules/X_Publisher.py.",
        ],
    }


def social_package(name: str, platforms: Optional[List[str]] = None) -> Dict[str, Any]:
    draft = build_draft(name, format="short")
    social = load_social()
    plats = platforms or ["tiktok", "youtube", "x"]
    packages = []
    for p in plats:
        meta = social.get("platforms", {}).get(p, {})
        packages.append(
            {
                "platform": p,
                "handle": meta.get("handle", ""),
                "caption": (
                    f"{draft['name']}: honest first take. "
                    f"{draft['shape']['verdict']} "
                    f"{'Link in bio / description.' if p != 'x' else draft.get('affiliate_link', '')}"
                )[:220],
                "upload_mode": meta.get("upload_mode", "manual_assisted"),
                "requires_approval": REQUIRE_POST_APPROVAL,
            }
        )
    entry = {
        "id": uuid4().hex[:10],
        "item": draft["name"],
        "created_at": _now_iso(),
        "status": "awaiting_approval",
        "packages": packages,
        "script": draft["script"],
    }
    social.setdefault("queue", []).append(entry)
    save_social(social)
    return entry


def social_queue() -> List[Dict[str, Any]]:
    return load_social().get("queue", [])


def sponsors_find(lane: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    prospects = load_sponsors().get("prospects", [])
    if lane:
        lane = lane.lower()
        prospects = [p for p in prospects if lane in (p.get("lanes") or [])]
    # Prefer preferred content lanes when no filter
    if not lane:
        prospects = sorted(
            prospects,
            key=lambda p: (
                0 if any(l in PREFERRED_LANES for l in p.get("lanes", [])) else 1,
                -int(p.get("fit", 0)),
            ),
        )
    else:
        prospects = sorted(prospects, key=lambda p: -int(p.get("fit", 0)))
    return prospects[:limit]


def _social_handles() -> Dict[str, str]:
    """Live handles for pitch copy — prefers social_connections.json."""
    social = load_social()
    plats = social.get("platforms") or {}

    def _h(key: str, fallback: str) -> str:
        raw = (plats.get(key) or {}).get("handle") or fallback
        return str(raw).strip()

    twitch = _h("twitch", "ItsSimplyBilly").lstrip("@")
    tiktok = _h("tiktok", "@itssimplybilly")
    if not tiktok.startswith("@"):
        tiktok = f"@{tiktok}"
    youtube = _h("youtube", "@SimplyBilly")
    if not youtube.startswith("@"):
        youtube = f"@{youtube}"
    x = _h("x", "@SimplyBilly_")
    if not x.startswith("@"):
        x = f"@{x}"
    return {
        "twitch": twitch,
        "tiktok": tiktok,
        "tiktok_bare": tiktok.lstrip("@"),
        "youtube": youtube,
        "youtube_bare": youtube.lstrip("@"),
        "x": x,
        "x_bare": x.lstrip("@"),
    }


def sponsors_pitch(name: str) -> Dict[str, str]:
    data = load_sponsors()
    match = None
    key = name.lower()
    for p in data.get("prospects", []):
        if key in p.get("name", "").lower() or p.get("id") == key:
            match = p
            break
    brand = match["name"] if match else name
    lanes = ", ".join((match or {}).get("lanes", PREFERRED_LANES))
    h = _social_handles()
    subject = f"Review opportunity — SimplyBilly × {brand}"
    body = f"""Hi {brand} team,

I'm William (SimplyBilly) — I create game and tech testing content on TikTok ({h['tiktok']}), Twitch ({h['twitch']}), YouTube ({h['youtube']}), and X ({h['x']}).

I'd like to create an honest review of a {brand} product for my audience. My style is practical: what it is, real-world use, what works, what gets in the way, and who it's actually for.

Deliverables I can provide:
- Short-form review (TikTok + YouTube Shorts)
- Stream segment or longer YouTube review when it fits
- Affiliate tracking where appropriate (Amazon tag billycarter-20 / brand program)
- Clear FTC disclosure

Media kit available on request. Happy to start with a product that fits {lanes}.

Thanks,
William
TikTok: tiktok.com/{h['tiktok_bare']}
Twitch: twitch.tv/{h['twitch']}
YouTube: youtube.com/{h['youtube_bare']}
X: x.com/{h['x_bare']}
"""
    if match:
        match.setdefault("outreach", []).append(
            {"status": "pitch_drafted", "at": _now_iso()}
        )
        if match.get("status") == "prospect":
            match["status"] = "pitch_ready"
        save_sponsors(data)
    return {"subject": subject, "body": body, "brand": brand}


def sponsors_log(name: str, status: str, note: str = "") -> Dict[str, Any]:
    data = load_sponsors()
    key = name.lower()
    for p in data.get("prospects", []):
        if key in p.get("name", "").lower() or p.get("id") == key:
            p["status"] = status
            p.setdefault("outreach", []).append(
                {"status": status, "note": note, "at": _now_iso()}
            )
            save_sponsors(data)
            return p
    # create new
    row = {
        "id": _slug(name),
        "name": name,
        "lanes": PREFERRED_LANES,
        "type": "brand",
        "fit": 5,
        "why": note or "Added manually",
        "status": status,
        "outreach": [{"status": status, "note": note, "at": _now_iso()}],
        "added_at": _now_iso(),
    }
    data.setdefault("prospects", []).append(row)
    save_sponsors(data)
    return row


# ---------------------------------------------------------------------------
# M13: live sponsor research enrichment + pipeline
#
# M13 is "live sponsor research enrichment". The static seed in
# sponsors.json is a starting list of 10 hand-picked brands. "Live"
# enrichment means: as you do research and outreach, the list grows
# with notes, links, contact attempts, and real pipeline state.
#
# This adds three things on top of the existing seed:
#   - sponsors_add(): proper creation (vs the side-effect in
#     sponsors_log), with lanes, type, fit, and an initial note.
#   - sponsors_enrich(): append a timestamped note/link to an
#     existing prospect without changing its pipeline state.
#   - sponsors_pipeline(): a per-stage summary so manage status can
#     show the real outreach state, not just "10 prospects".
# ---------------------------------------------------------------------------

PIPELINE_STAGES = (
    "prospect",      # not contacted yet
    "pitch_ready",   # pitch drafted, not sent
    "contacted",     # pitch sent, awaiting reply
    "replied",       # they responded (positive or negative)
    "negotiating",   # terms/deal in discussion
    "won",           # deal closed
    "lost",          # passed / no fit
    "shelved",       # paused, revisit later
)


def sponsors_add(
    name: str,
    lanes: Optional[List[str]] = None,
    type: str = "brand",
    fit: int = 5,
    contact: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """Create a new sponsor prospect. De-dupes by case-insensitive
    name: if a prospect with this name already exists, return it
    unchanged rather than creating a duplicate.

    `lanes` is a list like ['game', 'tech']. Defaults to
    PREFERRED_LANES if not given.
    """
    data = load_sponsors()
    name_key = name.strip()
    if not name_key:
        raise ValueError("Sponsor name cannot be empty.")
    for p in data.get("prospects", []):
        if p.get("name", "").lower() == name_key.lower():
            return p  # de-dupe: caller can enrich if they want
    lanes = lanes or list(PREFERRED_LANES)
    # Filter to valid lanes; warn silently on unknowns.
    lanes = [l for l in lanes if l in LANES] or list(PREFERRED_LANES)
    fit = max(1, min(10, int(fit)))
    row = {
        "id": _slug(name_key),
        "name": name_key,
        "lanes": lanes,
        "type": type,
        "fit": fit,
        "contact": contact,
        "why": note or "Added via bolt sponsors add",
        "status": "prospect",
        "outreach": [],
        "notes": [{"text": note, "at": _now_iso()}] if note else [],
        "added_at": _now_iso(),
    }
    data.setdefault("prospects", []).append(row)
    save_sponsors(data)
    return row


def sponsors_enrich(name: str, note: str = "", link: str = "", mark_contacted: bool = False) -> Dict[str, Any]:
    """Append a timestamped note (and optional link) to an existing
    prospect. Optionally also advance status from 'pitch_ready' to
    'contacted' if you mark_contacted=True — i.e. "I just sent the
    pitch email, here's the link to the thread".

    The note/link is stored in the prospect's `notes` array (not
    `outreach`, which is reserved for pipeline transitions). The
    `outreach` array gets a new entry only if mark_contacted=True.
    """
    data = load_sponsors()
    key = name.lower()
    for p in data.get("prospects", []):
        if key in p.get("name", "").lower() or p.get("id") == key:
            entry = {"at": _now_iso()}
            if note:
                entry["text"] = note
            if link:
                entry["link"] = link
            p.setdefault("notes", []).append(entry)
            if mark_contacted:
                p["status"] = "contacted"
                p.setdefault("outreach", []).append(
                    {"status": "contacted", "note": note or link, "at": _now_iso()}
                )
            save_sponsors(data)
            return p
    raise ValueError(
        f"No sponsor prospect matching '{name}'. Add it first with "
        f"`bolt sponsors add \"{name}\"`."
    )


# ---------------------------------------------------------------------------
# M13: live web-research enrichment
#
# The above functions are operator-typed. sponsors_research() is the
# live part: it takes a web-search query (and the results it returned),
# attaches them to a prospect as a timestamped `research` entry, and
# optionally updates the prospect's `why`/`contact` fields based on
# what was found.
#
# Decoupled from the network on purpose: the caller passes in the
# search results, so the function is testable without internet. The
# CLI command `bolt manage sponsors-research NAME QUERY` is the
# caller that actually fetches results (via the project's web_search
# helper or a similar tool).
# ---------------------------------------------------------------------------


def sponsors_research(
    name: str,
    query: str,
    results: List[Dict[str, str]],
    update_contact: bool = True,
) -> Dict[str, Any]:
    """Attach web-search findings to a sponsor prospect.

    `results` is a list of {"url", "title", "description"} dicts
    (the shape the standard web_search tool returns). The function
    stores the query and the results as a single `research` entry on
    the prospect, and — if `update_contact` is True and a contact
    email was found in the results — sets the prospect's `contact`
    field to the first plausible email address.

    Returns the updated prospect row.
    """
    if not query.strip():
        raise ValueError("Research query cannot be empty.")
    data = load_sponsors()
    key = name.lower()
    for p in data.get("prospects", []):
        if key in p.get("name", "").lower() or p.get("id") == key:
            # Drop empty/None entries; keep only dicts with at least
            # a url or title so the saved data stays useful.
            cleaned = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                if r.get("url") or r.get("title"):
                    cleaned.append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "description": r.get("description", "")[:500],
                    })
            entry = {
                "at": _now_iso(),
                "query": query,
                "results": cleaned,
                "result_count": len(cleaned),
            }
            p.setdefault("research_log", []).append(entry)

            if update_contact and not p.get("contact"):
                email = _extract_first_email(cleaned)
                if email:
                    p["contact"] = email
                    p.setdefault("notes", []).append({
                        "at": _now_iso(),
                        "text": f"Auto-set contact from research query '{query}': {email}",
                    })
            save_sponsors(data)
            return p
    raise ValueError(
        f"No sponsor prospect matching '{name}'. Add it first with "
        f"`bolt sponsors add \"{name}\"`."
    )


import re as _re  # local alias to avoid shadowing any other `re`


def _extract_first_email(results: List[Dict[str, str]]) -> str:
    """Pull the first plausible email address out of search-result
    descriptions. Looks for `name@domain.tld` patterns. Stops at the
    first hit and returns it lowercased. Returns "" if nothing found.
    """
    pattern = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    for r in results:
        for field in ("description", "title", "url"):
            text = r.get(field, "") or ""
            match = pattern.search(text)
            if match:
                # Skip common noreply/no-reply variants — they can't
                # be replied to.
                lower = match.group(0).lower()
                if lower.startswith(("noreply", "no-reply", "donotreply", "do-not-reply")):
                    continue
                return lower
    return ""


def sponsors_pipeline() -> Dict[str, Any]:
    """Summarize the sponsor pipeline so `manage status` can show
    where the outreach actually stands.

    Returns a dict with:
      - by_stage: count per PIPELINE_STAGES (zero-filled)
      - total: total prospect count
      - active: anything not in (won, lost, shelved)
      - oldest_untouched: the prospect whose last note is oldest, as
        a nudge to revisit
      - top_fit_uncontacted: the highest-fit prospect still in
        'prospect' or 'pitch_ready' stage, for the next action
    """
    data = load_sponsors()
    prospects = data.get("prospects", [])

    by_stage = {stage: 0 for stage in PIPELINE_STAGES}
    for p in prospects:
        stage = p.get("status", "prospect")
        if stage in by_stage:
            by_stage[stage] += 1
        else:
            by_stage["prospect"] += 1  # unknown stage counts as prospect

    active = sum(
        v for k, v in by_stage.items() if k not in ("won", "lost", "shelved")
    )

    # Find the prospect whose last contact/note is oldest.
    def _last_ts(p: Dict[str, Any]) -> str:
        timestamps = []
        for entry in p.get("outreach", []) + p.get("notes", []):
            if "at" in entry:
                timestamps.append(entry["at"])
        if timestamps:
            return max(timestamps)
        return p.get("added_at", "")

    untouched = None
    if prospects:
        candidates = [p for p in prospects if p.get("status") not in ("won", "lost")]
        if candidates:
            untouched = min(candidates, key=_last_ts)

    # Highest-fit uncontacted prospect.
    uncontacted = [
        p for p in prospects
        if p.get("status") in ("prospect", "pitch_ready")
    ]
    top_fit = None
    if uncontacted:
        top_fit = max(uncontacted, key=lambda p: int(p.get("fit", 0)))

    return {
        "total": len(prospects),
        "active": active,
        "by_stage": by_stage,
        "oldest_untouched": (
            {"name": untouched.get("name"), "last_touched_at": _last_ts(untouched)}
            if untouched else None
        ),
        "top_fit_uncontacted": (
            {"name": top_fit.get("name"), "fit": top_fit.get("fit")}
            if top_fit else None
        ),
    }


def business_lesson() -> str:
    _ensure_seed_files()
    lessons = [
        "Proof before pitches: one honest game/tech review online beats ten unsent emails.",
        f"Every product mention should carry tag {AMAZON_TAG} when it is an Amazon link.",
        "Disclose clearly. Trust is the product.",
        "Pitch 5 brands only after you have something to show — even if views are low.",
        "Pick one item in testing. Journal it. Film it. Post it. Then upgrade Bolt.",
        "Twitch builds personality; TikTok builds discovery; YouTube builds depth; Amazon converts.",
    ]
    # rotate by day of year
    idx = date.today().timetuple().tm_yday % len(lessons)
    return lessons[idx]


def advance_next() -> Dict[str, str]:
    _ensure_seed_files()
    steps = [
        {
            "title": "Use Content Manager daily for game/tech items",
            "why": "Catalog + notes are the foundation for reviews and storefront links.",
            "command": "bolt manage next",
        },
        {
            "title": "Run Good Morning Bolt each day",
            "why": "Spoken briefing removes decision paralysis.",
            "command": "bolt morning",
        },
        {
            "title": "Attach ASINs to storefront items you already own",
            "why": "Affiliate revenue needs tracked links on real reviews.",
            "command": "bolt store feature-next",
        },
        {
            "title": "Package one post for social (approval required)",
            "why": "Cross-post planning without auto-posting risk.",
            "command": 'bolt social package "ITEM"',
        },
        {
            "title": "Draft one sponsor pitch this week",
            "why": "Outreach compounds only if it starts.",
            "command": "bolt sponsors next",
        },
    ]
    idx = date.today().timetuple().tm_yday % len(steps)
    return steps[idx]


def build_morning_briefing() -> Dict[str, Any]:
    actions = next_actions(limit=3)
    testing = list_items(status="testing")
    store = store_feature_next()
    sponsors = sponsors_find(limit=3)
    lesson = business_lesson()
    advance = advance_next()
    ship = shipped_summary()

    lines = [
        f"Good morning, {CREATOR_NAME}. Bolt is online.",
        f"Focus lanes today: games and tech.",
        f"Items currently testing: {len(testing)}.",
        f"Shipped reviews: {ship['total']} (last: {ship['last_posted_at'] or 'never'}).",
    ]
    if testing:
        lines.append(f"Top test item: {testing[0]['name']}.")
    if actions:
        lines.append(f"Content action: {actions[0]['title']}.")
    biz = next((a for a in actions if a["type"] == "business"), None)
    if biz:
        lines.append(f"Business action: {biz['title']}.")
    lines.append(f"Bolt advance: {advance['title']}.")
    lines.append(f"Business lesson: {lesson}")
    if store.get("feature"):
        lines.append(f"Storefront feature idea: {store['feature']['name']}.")
    if sponsors:
        lines.append(f"Hopeful partner to research: {sponsors[0]['name']}.")
    lines.append("All social posts still need your approval. Let's make something real today.")

    spoken = " ".join(lines)
    # Shorter voice line for TTS (full `spoken` stays in the markdown).
    # Long paragraphs take minutes to read and feel broken mid-sentence if cut.
    voice_bits = [
        f"Good morning, {CREATOR_NAME}. Bolt is online.",
        f"Focus: games and tech. {len(testing)} item(s) in testing.",
    ]
    if testing:
        voice_bits.append(f"Top item: {testing[0]['name']}.")
    if actions:
        voice_bits.append(f"Content: {actions[0]['title']}.")
    if biz:
        voice_bits.append(f"Business: {biz['title']}.")
    voice_bits.append(f"Advance Bolt: {advance['title']}.")
    voice_bits.append("All posts still need your approval.")
    spoken_voice = " ".join(voice_bits)

    md_lines = [
        f"# Good Morning Bolt — {date.today().isoformat()}",
        "",
        f"Creator: {CREATOR_NAME}",
        f"Priority lanes: {', '.join(PREFERRED_LANES)}",
        f"Amazon tag: `{AMAZON_TAG}`",
        f"Posting: approval required = {REQUIRE_POST_APPROVAL}",
        "",
        "## Spoken Briefing",
        spoken,
        "",
        "## Next Actions",
    ]
    for a in actions:
        md_lines.append(f"- **{a['type']}**: {a['title']} — {a['why']}")
        md_lines.append(f"  - `{a['command']}`")
    md_lines.extend(
        [
            "",
            "## Storefront",
            store.get("message", ""),
            f"Command: `{store.get('command', '')}`",
            "",
            "## Sponsor Watchlist",
        ]
    )
    for s in sponsors:
        md_lines.append(f"- {s['name']} (fit {s.get('fit')}): {s.get('why')}")
    md_lines.extend(["", "## Business Lesson", lesson, "", "## Advance Bolt", advance["title"], advance["why"], f"`{advance['command']}`", ""])

    path = BRIEFINGS_DIR / f"morning_{date.today().isoformat()}.md"
    path.write_text("\n".join(md_lines), encoding="utf-8")
    latest = BRIEFINGS_DIR / "latest_morning.md"
    latest.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "spoken": spoken,
        "spoken_voice": spoken_voice,
        "actions": actions,
        "path": str(path),
        "lesson": lesson,
        "advance": advance,
        "store": store,
        "sponsors": sponsors,
    }


def morning(speak_aloud: bool = True) -> Dict[str, Any]:
    briefing = build_morning_briefing()
    # Print the full spoken paragraph so terminal still has the complete brief.
    print(briefing.get("spoken") or "")
    if briefing.get("path"):
        print(f"\nSaved: {briefing['path']}")
    if speak_aloud:
        try:
            from modules.Bolt_Voice import speak

            # wait=True: CLI exits after morning(); async speak would be killed
            # before the daemon TTS worker plays anything.
            spoken = (
                (briefing.get("spoken_voice") or briefing.get("spoken") or "")
            ).strip()
            if spoken:
                print("Speaking morning briefing…")
                speak(spoken, wait=True)
        except Exception as exc:
            print(f"[voice fallback] {exc}")
            # Last resort: macOS say in-process so voice still works if
            # Bolt_Voice misconfigures.
            try:
                import subprocess

                subprocess.run(
                    [
                        "say",
                        (
                            briefing.get("spoken_voice")
                            or briefing.get("spoken")
                            or "Good morning."
                        ),
                    ],
                    check=False,
                )
            except Exception:
                pass
    return briefing


def is_good_morning_phrase(text: str) -> bool:
    t = re.sub(r"[^a-z\s]", "", (text or "").lower()).strip()
    patterns = (
        "good morning bolt",
        "good morning bolt!",
        "morning bolt",
        "hey bolt good morning",
        "bolt good morning",
    )
    return any(p in t for p in patterns) or t in {"good morning", "morning bolt"}


# ── CLI ──────────────────────────────────────────────────────────────────────


def _print_item(item: Dict[str, Any]) -> None:
    notes = len(item.get("notes_log") or [])
    print(
        f"  - {item.get('name')} [{item.get('lane')}/{item.get('status')}] "
        f"notes={notes} id={item.get('id')}"
    )


# ── Friendly CLI helpers (typos, short names, platform flags) ─────────────────

# Canonical subcommand names accepted by argparse.
_CANONICAL_CMDS = [
    "add", "list", "note", "draft", "mark-ready", "mark-posted", "shipped",
    "post", "post-dry-run", "tiktok-status", "youtube-pkg", "x-pkg",
    "youtube-status", "x-status", "sponsors-add", "sponsors-enrich",
    "sponsors-pipeline", "sponsors-research", "model-inspect", "model-status",
    "next", "status", "store-add", "store-list", "store-feature-next",
    "social-status", "social-package", "social-queue", "sponsors-find",
    "sponsors-pitch", "sponsors-log", "sponsors-next", "business-lesson",
    "business-next", "advance-next", "morning", "help",
]

# Short / typo aliases → canonical. Keep this list human-friendly.
_CMD_ALIASES = {
    # mark-ready
    "ready": "mark-ready",
    "markready": "mark-ready",
    "mark_ready": "mark-ready",
    "mark-reade": "mark-ready",   # common typo
    "reade": "mark-ready",
    "mark-rady": "mark-ready",
    # mark-posted
    "posted": "mark-posted",
    "post-it": "mark-posted",
    "ship": "mark-posted",
    "shipped-item": "mark-posted",
    "markposted": "mark-posted",
    "mark_posted": "mark-posted",
    "mark-post": "mark-posted",
    # common shortenings
    "ls": "list",
    "stat": "status",
    "st": "status",
    "n": "next",
    "gm": "morning",
    "good-morning": "morning",
    "goodmorning": "morning",
}

# Platform flag / token → stored platform id
_PLATFORM_ALIASES = {
    "tiktok": "tiktok",
    "tt": "tiktok",
    "youtube": "youtube_shorts",
    "yt": "youtube_shorts",
    "shorts": "youtube_shorts",
    "youtube_shorts": "youtube_shorts",
    "youtube-shorts": "youtube_shorts",
    "x": "x",
    "twitter": "x",
    "amazon": "amazon",
    "amz": "amazon",
    "store": "amazon",
    "storefront": "amazon",
}

_DAILY_CHEATSHEET = """
Bolt manage — daily cheat sheet (short names work)
──────────────────────────────────────────────────
  bolt manage status                 What's next overall
  bolt manage next                   Top actions
  bolt manage list                   Catalog items
  bolt manage add "Name" --lane tech --asin B0…
  bolt manage note "Name" --text "…"
  bolt manage draft "Name"
  bolt manage ready "Name"           (alias: mark-ready)
  bolt manage posted "Name" --amazon --where "https://…"
                                      # Amazon-only is valid (no social required)
  bolt manage posted "Name" --tiktok --youtube --x
                                      # only if you actually posted there
  bolt manage shipped
  bolt manage morning

Platforms (any casing, pick what you really used):
  --amazon   --tiktok   --youtube/--yt   --x/--twitter
Or: --platforms amazon   /   --platforms tiktok,youtube_shorts,x
No default platforms — say where it went or Bolt won't invent socials.

Typos are OK when close — Bolt will suggest the right command.
Full list: bolt manage help
""".strip()


def _normalize_platform_token(token: str) -> Optional[str]:
    key = (token or "").strip().lower().replace(" ", "_")
    if not key:
        return None
    return _PLATFORM_ALIASES.get(key) or (key if key in _PLATFORM_ALIASES.values() else None)


def _platforms_from_args(args: argparse.Namespace) -> List[str]:
    """Build platform list from --platforms and/or convenience flags."""
    found: List[str] = []
    raw = getattr(args, "platforms", None)
    if raw:
        for part in str(raw).split(","):
            p = _normalize_platform_token(part)
            if p and p not in found:
                found.append(p)
    for flag, plat in (
        ("tiktok", "tiktok"),
        ("youtube", "youtube_shorts"),
        ("x", "x"),
        ("amazon", "amazon"),
    ):
        if getattr(args, flag, False) and plat not in found:
            found.append(plat)
    # No silent default — social is optional. Billy often ships Amazon-only
    # reviews; inventing tiktok/youtube/x made the log lie.
    return found


def _normalize_manage_argv(argv: Sequence[str]) -> Tuple[List[str], Optional[str]]:
    """Rewrite friendly aliases + case-insensitive platform flags.

    Returns (new_argv, error_message_or_None).
    On a single close fuzzy match, auto-corrects and prints nothing (caller
    can mention the rewrite). On multiple/zero matches for typos, returns
    an error string.
    """
    if not argv:
        return [], None
    argv = list(argv)
    raw_cmd = argv[0]
    cmd = raw_cmd.lower().strip().lstrip("-")

    if cmd in ("help", "h", "?", "commands", "cheatsheet", "cheat"):
        return ["help"], None

    if cmd in _CMD_ALIASES:
        argv[0] = _CMD_ALIASES[cmd]
    elif cmd in _CANONICAL_CMDS:
        argv[0] = cmd
    else:
        pool = list(_CANONICAL_CMDS) + list(_CMD_ALIASES.keys())
        matches = difflib.get_close_matches(cmd, pool, n=3, cutoff=0.58)
        display: List[str] = []
        for m in matches:
            canon = _CMD_ALIASES.get(m, m)
            if canon not in display:
                display.append(canon)
        if len(display) == 1:
            # Auto-correct obvious typos like mark-reade → mark-ready
            print(f"(interpreted '{raw_cmd}' as '{display[0]}')", file=sys.stderr)
            argv[0] = display[0]
        elif display:
            hint = (
                f"Unknown command '{raw_cmd}'. Did you mean: "
                + ", ".join(f"`{d}`" for d in display)
                + "?\n"
                "Short forms: ready · posted · ship · list · status · next · morning\n"
                "Cheat sheet: bolt manage help"
            )
            return argv, hint
        else:
            hint = (
                f"Unknown command '{raw_cmd}'.\n"
                "Short forms: ready · posted · ship · list · status · next · morning\n"
                "Cheat sheet: bolt manage help"
            )
            return argv, hint

    # Lowercase known platform flags: --Amazon → --amazon, --YouTube → --youtube
    known_flags = {
        "--tiktok", "--tt", "--youtube", "--yt", "--shorts",
        "--x", "--twitter", "--amazon", "--amz", "--store", "--storefront",
    }
    flag_map = {
        "--tt": "--tiktok",
        "--yt": "--youtube",
        "--shorts": "--youtube",
        "--twitter": "--x",
        "--amz": "--amazon",
        "--store": "--amazon",
        "--storefront": "--amazon",
    }
    out: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        low = a.lower() if a.startswith("-") else a
        if low in known_flags or low in flag_map:
            out.append(flag_map.get(low, low))
            i += 1
            continue
        # --platforms=Amazon,TikTok style
        if low.startswith("--platforms="):
            _, _, val = a.partition("=")
            parts = []
            for p in val.split(","):
                n = _normalize_platform_token(p)
                if n:
                    parts.append(n)
            out.append("--platforms=" + ",".join(parts) if parts else "--platforms=")
            i += 1
            continue
        out.append(a)
        i += 1
    return out, None


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_seed_files()
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    if not raw_argv or raw_argv[0] in ("-h", "--help"):
        print(_DAILY_CHEATSHEET)
        print()
        # fall through to full argparse help below with empty → status-ish
        if not raw_argv:
            raw_argv = ["status"]

    normalized, err = _normalize_manage_argv(raw_argv)
    if err:
        print(err, file=sys.stderr)
        return 2

    if normalized and normalized[0] == "help":
        print(_DAILY_CHEATSHEET)
        return 0

    parser = argparse.ArgumentParser(
        prog="bolt manage",
        description="Bolt Content Manager — use short names: ready, posted, ship, status, next",
    )
    sub = parser.add_subparsers(dest="cmd")

    # manage
    p_add = sub.add_parser("add", help="Add catalog item")
    p_add.add_argument("name")
    p_add.add_argument("--lane", default="tech", choices=LANES)
    p_add.add_argument("--status", default="testing", choices=STATUSES)
    p_add.add_argument("--asin", default="")
    p_add.add_argument("--notes", default="")

    p_list = sub.add_parser("list", help="List catalog")
    p_list.add_argument("--lane", default=None)
    p_list.add_argument("--status", default=None)

    p_note = sub.add_parser("note", help="Add test journal note")
    p_note.add_argument("name")
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--day", type=int, default=None)

    p_draft = sub.add_parser("draft", help="Build review draft")
    p_draft.add_argument("name")
    p_draft.add_argument("--format", default="short", choices=["short", "long"])

    p_ready = sub.add_parser("mark-ready", help="Mark a draft as ready to post (alias: ready)")
    p_ready.add_argument("name")
    p_ready.add_argument("--verdict", default="")
    p_ready.add_argument("--note", default="")

    p_posted = sub.add_parser(
        "mark-posted",
        help="Record a review as shipped (alias: posted / ship)",
    )
    p_posted.add_argument("name")
    p_posted.add_argument(
        "--platforms",
        default=None,
        help="Comma list: tiktok,youtube_shorts,x,amazon (or use flags below)",
    )
    p_posted.add_argument("--where", default="", help="URL or video ID of the post")
    p_posted.add_argument("--note", default="")
    p_posted.add_argument("--tiktok", action="store_true", help="Logged on TikTok")
    p_posted.add_argument("--youtube", action="store_true", help="Logged on YouTube Shorts")
    p_posted.add_argument("--x", action="store_true", help="Logged on X/Twitter")
    p_posted.add_argument("--amazon", action="store_true", help="Logged Amazon/storefront link")

    sub.add_parser("shipped", help="List shipped reviews")

    p_post = sub.add_parser(
        "post", help="Publish a ready catalog item to TikTok (approval-gated)"
    )
    p_post.add_argument("name")
    p_post.add_argument(
        "--approve", action="store_true",
        help="Required. Without it, the publish is a dry-run.",
    )
    p_post.add_argument(
        "--video", default=None,
        help="Override the video file (default: look in media/clips/<id>.mp4)",
    )

    p_dry = sub.add_parser(
        "post-dry-run", help="Show what a post would do without touching the network"
    )
    p_dry.add_argument("name")

    sub.add_parser(
        "tiktok-status",
        help="Report what's blocking a real TikTok publish (creds, scope, etc.)",
    )

    p_yt = sub.add_parser(
        "youtube-pkg",
        help="Build a YouTube-ready upload package (manual-assist, M12)",
    )
    p_yt.add_argument("name")

    p_x = sub.add_parser(
        "x-pkg", help="Build an X (Twitter)-ready post body (manual-assist, M12)"
    )
    p_x.add_argument("name")

    sub.add_parser("youtube-status", help="YouTube publishing readiness")
    sub.add_parser("x-status", help="X publishing readiness")

    p_sadd = sub.add_parser("sponsors-add", help="Add a new sponsor prospect")
    p_sadd.add_argument("name")
    p_sadd.add_argument("--lanes", default="", help="comma-separated, e.g. game,tech")
    p_sadd.add_argument("--type", default="brand")
    p_sadd.add_argument("--fit", type=int, default=5)
    p_sadd.add_argument("--contact", default="")
    p_sadd.add_argument("--note", default="")

    p_senrich = sub.add_parser("sponsors-enrich", help="Add a note/link to a prospect")
    p_senrich.add_argument("name")
    p_senrich.add_argument("--note", default="")
    p_senrich.add_argument("--link", default="")
    p_senrich.add_argument("--mark-contacted", action="store_true",
                            help="Also advance status to 'contacted'")

    sub.add_parser("sponsors-pipeline", help="Show sponsor outreach pipeline summary")

    p_sres = sub.add_parser(
        "sponsors-research",
        help="Run a web search and attach findings to a sponsor prospect",
    )
    p_sres.add_argument("name")
    p_sres.add_argument("query", help="Search query, e.g. 'Razer creator program'")
    p_sres.add_argument("--limit", type=int, default=5)
    p_sres.add_argument("--no-update-contact", action="store_true",
                          help="Don't auto-fill the contact field from results")
    p_sres.add_argument("--json", action="store_true",
                          help="Output the raw search results as JSON instead of the prospect row")

    p_inspect = sub.add_parser(
        "model-inspect",
        help="Show the learned clip-ranking model state (per game, per trigger)",
    )
    p_inspect.add_argument("--game", default=None, help="Limit to one game")

    sub.add_parser("model-status", help="Show learning loop summary")

    sub.add_parser("next", help="Show next actions")
    sub.add_parser("status", help="Manager status snapshot")

    # store
    p_sadd = sub.add_parser("store-add", help="Add Amazon storefront item")
    p_sadd.add_argument("--name", required=True)
    p_sadd.add_argument("--asin", default="")
    p_sadd.add_argument("--category", default="tech")
    p_sadd.add_argument("--notes", default="")
    sub.add_parser("store-list")
    sub.add_parser("store-feature-next")

    # social
    sub.add_parser("social-status")
    p_pkg = sub.add_parser("social-package")
    p_pkg.add_argument("name")
    p_pkg.add_argument("--platforms", default="tiktok,youtube,x")
    sub.add_parser("social-queue")

    # sponsors
    p_find = sub.add_parser("sponsors-find")
    p_find.add_argument("--lane", default=None)
    p_find.add_argument("--limit", type=int, default=5)
    p_pitch = sub.add_parser("sponsors-pitch")
    p_pitch.add_argument("name")
    p_log = sub.add_parser("sponsors-log")
    p_log.add_argument("name")
    p_log.add_argument("--status", required=True)
    p_log.add_argument("--note", default="")
    sub.add_parser("sponsors-next")

    # business / advance / morning
    sub.add_parser("business-lesson")
    sub.add_parser("business-next")
    sub.add_parser("advance-next")
    p_m = sub.add_parser("morning")
    p_m.add_argument("--speak", action="store_true", default=True)
    p_m.add_argument("--quiet", action="store_true")

    # Use normalized argv so aliases / platform flags apply
    try:
        args = parser.parse_args(normalized)
    except SystemExit as e:
        # argparse already printed usage; add cheat sheet pointer on errors
        code = e.code if isinstance(e.code, int) else 2
        if code:
            print("\nTip: bolt manage help   ·   short: ready · posted · ship · status", file=sys.stderr)
        return code or 0
    if not args.cmd:
        print(_DAILY_CHEATSHEET)
        return 0

    try:
        if args.cmd == "add":
            item = add_item(args.name, args.lane, args.status, args.notes, args.asin)
            print(f"Added/updated: {item['name']} ({item['lane']}/{item['status']})")
        elif args.cmd == "list":
            for item in list_items(args.lane, args.status):
                _print_item(item)
        elif args.cmd == "note":
            item = add_note(args.name, args.text, args.day)
            print(f"Note added to {item['name']} (total notes: {len(item.get('notes_log', []))})")
        elif args.cmd == "draft":
            draft = build_draft(args.name, args.format)
            print(draft["script"])
            print(f"\nAffiliate: {draft['affiliate_link']}")
        elif args.cmd == "mark-ready":
            item = mark_ready(args.name, verdict=args.verdict, note=args.note)
            print(f"Marked ready: {item['name']} (status={item['status']})")
            print(f"Next: bolt manage posted \"{item['name']}\" --tiktok --youtube --x")
            print(f"  or: bolt manage posted \"{item['name']}\" --amazon --where <url>")
        elif args.cmd == "mark-posted":
            plats = _platforms_from_args(args)
            if not plats and not (args.where or args.note):
                print(
                    "Where did you post it? Name at least one platform "
                    "(no silent social default):\n"
                    f"  bolt manage posted \"{args.name}\" --amazon --where <url>\n"
                    f"  bolt manage posted \"{args.name}\" --tiktok --youtube --x\n"
                    f"  bolt manage posted \"{args.name}\" --platforms amazon",
                    file=sys.stderr,
                )
                return 2
            result = mark_posted(
                args.name, platforms=plats, where=args.where, note=args.note
            )
            final_plats = result.get("platforms") or plats
            verb = "Updated" if result.get("updated") else "Posted"
            print(
                f"{verb}: {result['catalog_item']['name']} -> "
                f"{final_plats or '(no platforms)'}"
            )
            print(f"Review entry: {result['review_entry']['id']}")
            if final_plats == ["amazon"] or (
                len(final_plats) == 1 and final_plats[0] == "amazon"
            ):
                print(
                    "Logged Amazon-only — fine. Social shorts are optional, "
                    "not required for a real ship."
                )
        elif args.cmd == "shipped":
            for r in shipped_reviews():
                plats = ",".join(r.get("platforms", [])) or "-"
                where = r.get("where", "") or "-"
                print(f"  {r['posted_at']} {r['name']} [{r.get('lane')}] {plats} {where}")
        elif args.cmd == "post":
            result = tiktok_publish_item(
                args.name, approve=args.approve, video_path=args.video
            )
            print(json.dumps(result, indent=2, default=str))
        elif args.cmd == "post-dry-run":
            result = tiktok_publish_dry_run(args.name)
            print(json.dumps(result, indent=2, default=str))
        elif args.cmd == "tiktok-status":
            st = tiktok_publish_status()
            for c in st["checks"]:
                mark = "OK  " if c["ok"] else "MISS"
                print(f"  [{mark}] {c['name']}: {c['detail']}")
            print()
            if st["ready"]:
                print("Publisher is ready. Run `bolt manage post \"NAME\" --approve` to publish.")
            else:
                print("Publisher is NOT ready. Next steps:")
                for s in st["next_steps"]:
                    print(f"  - {s}")
        elif args.cmd == "youtube-pkg":
            pkg = build_youtube_package(args.name)
            print(json.dumps(pkg, indent=2, default=str))
        elif args.cmd == "x-pkg":
            pkg = build_x_package(args.name)
            print(json.dumps(pkg, indent=2, default=str))
        elif args.cmd == "youtube-status":
            st = youtube_readiness()
            for c in st["checks"]:
                mark = "OK  " if c["ok"] else "MISS"
                print(f"  [{mark}] {c['name']}: {c['detail']}")
            print()
            print("Next steps:")
            for s in st["next_steps"]:
                print(f"  - {s}")
        elif args.cmd == "x-status":
            st = x_readiness()
            for c in st["checks"]:
                mark = "OK  " if c["ok"] else "MISS"
                print(f"  [{mark}] {c['name']}: {c['detail']}")
            print()
            print("Next steps:")
            for s in st["next_steps"]:
                print(f"  - {s}")
        elif args.cmd == "sponsors-add":
            lanes = [l.strip() for l in args.lanes.split(",") if l.strip()]
            row = sponsors_add(
                args.name,
                lanes=lanes or None,
                type=args.type,
                fit=args.fit,
                contact=args.contact,
                note=args.note,
            )
            print(json.dumps(row, indent=2, default=str))
        elif args.cmd == "sponsors-enrich":
            row = sponsors_enrich(
                args.name, note=args.note, link=args.link,
                mark_contacted=args.mark_contacted,
            )
            print(json.dumps(row, indent=2, default=str))
        elif args.cmd == "sponsors-pipeline":
            p = sponsors_pipeline()
            print(f"Total prospects: {p['total']}  (active: {p['active']})")
            print("By stage:")
            for stage, count in p["by_stage"].items():
                print(f"  {stage:14s} {count}")
            if p["oldest_untouched"]:
                ot = p["oldest_untouched"]
                print(f"Oldest untouched: {ot['name']} (last {ot['last_touched_at'] or 'never'})")
            if p["top_fit_uncontacted"]:
                tf = p["top_fit_uncontacted"]
                print(f"Top uncontacted:  {tf['name']} (fit={tf['fit']})")
        elif args.cmd == "sponsors-research":
            # Try to use the project's web_search helper if available;
            # otherwise print a clear error so the operator can run
            # the search elsewhere and call sponsors_research directly.
            try:
                from scripts._research import web_search_results  # type: ignore
            except Exception:
                try:
                    from _research import web_search_results  # type: ignore
                except Exception:
                    web_search_results = None
            if web_search_results is None:
                print(
                    "No web_search helper available. Either run this from the "
                    "agent environment, or call sponsors_research() with results "
                    "you fetched yourself.",
                    file=sys.stderr,
                )
                sys.exit(2)
            results = web_search_results(args.query, limit=args.limit)
            if args.json:
                print(json.dumps(results, indent=2, default=str))
                return 0
            updated = sponsors_research(
                args.name,
                query=args.query,
                results=results,
                update_contact=not args.no_update_contact,
            )
            last = updated.get("research_log", [])[-1] if updated.get("research_log") else {}
            print(f"Attached {last.get('result_count', 0)} results to {updated['name']}.")
            if updated.get("contact"):
                print(f"Contact now: {updated['contact']}")
            print(json.dumps(updated, indent=2, default=str))
        elif args.cmd == "model-inspect":
            from modules.Clip_Ranker import inspect_learned_model, LEARNED_MIN_SAMPLES
            model = inspect_learned_model(game=args.game)
            print(f"Games with data: {model['summary']['total_games']}")
            print(
                f"Triggers with signal (>= {LEARNED_MIN_SAMPLES} samples): "
                f"{model['summary']['triggers_with_signal']}"
            )
            print(
                f"Triggers without signal: {model['summary']['triggers_without_signal']}"
            )
            print()
            for game, gdata in model["games"].items():
                if args.game and args.game != game:
                    continue
                print(f"=== {game} ===")
                for t in gdata["triggers"]:
                    print(
                        f"  {t['trigger']:14s} n={t['samples']:4d} "
                        f"avg_views={t['avg_views']:>8.0f} "
                        f"like_rate={t['like_rate']:.2%} "
                        f"boost={t['learned_boost']:>5.1f}"
                    )
                print()
        elif args.cmd == "model-status":
            from modules.Clip_Ranker import learning_loop_status
            ll = learning_loop_status()
            print(f"Total outcomes logged: {ll['total_outcomes']}")
            print(f"Last observation: {ll['last_observation_at'] or 'never'}")
            print(
                f"(game, trigger) pairs with signal: {ll['pairs_with_signal']} "
                f"of {ll['pairs_total']}"
            )
            if ll["top_boost"]:
                tb = ll["top_boost"]
                print(
                    f"Top boost: {tb['trigger']} on {tb['game']} "
                    f"(+{tb['boost']}, {tb['samples']} samples)"
                )
            else:
                print("No (game, trigger) pair has enough data yet.")
        elif args.cmd == "next":
            actions = next_actions()
            for a in actions:
                print(f"[{a['type']}] {a['title']}\n  why: {a['why']}\n  run: {a['command']}\n")
            try:
                from modules.Bolt_Voice import speak_result

                if actions:
                    speak_result(
                        "Next up: " + ". ".join(a["title"] for a in actions[:3])
                    )
                else:
                    speak_result("Nothing urgent is queued right now.")
            except Exception:
                pass
        elif args.cmd == "status":
            print(f"Creator: {CREATOR_NAME}")
            print(f"Preferred lanes: {PREFERRED_LANES}")
            print(f"Amazon tag: {AMAZON_TAG}")
            print(f"Approval required: {REQUIRE_POST_APPROVAL}")
            print(f"Catalog items: {len(list_items())}")
            summary = store_summary()
            print(
                f"Storefront items: {summary['total']} "
                f"({summary['with_asin']} with ASIN, "
                f"{summary['missing_asin']} missing ASIN)"
            )
            if summary["missing_asin"]:
                print(
                    "  M9 blockers (need ASINs to feature): "
                    + ", ".join(summary["missing_asin_names"])
                )
            ship = shipped_summary()
            by_lane_str = ", ".join(f"{k}:{v}" for k, v in sorted(ship["by_lane"].items())) or "none"
            print(
                f"Shipped reviews: {ship['total']} ({by_lane_str})"
            )
            if ship["last_posted_at"]:
                print(f"  last posted: {ship['last_posted_at']}")
            sp = sponsors_pipeline()
            stage_str = ", ".join(
                f"{k}:{v}" for k, v in sp["by_stage"].items() if v
            ) or "none"
            print(
                f"Sponsor pipeline: {sp['active']} active of {sp['total']} ({stage_str})"
            )
            if sp["top_fit_uncontacted"]:
                tf = sp["top_fit_uncontacted"]
                print(f"  next: pitch {tf['name']} (fit={tf['fit']})")
            # Learning loop: how much signal is the ranker model
            # actually working with?
            from modules.Clip_Ranker import learning_loop_status
            ll = learning_loop_status()
            print(
                f"Learning loop: {ll['pairs_with_signal']}/{ll['pairs_total']} "
                f"(game, trigger) pairs have signal "
                f"({ll['total_outcomes']} outcomes)"
            )
            if ll["top_boost"]:
                tb = ll["top_boost"]
                print(
                    f"  top boost: {tb['trigger']} on {tb['game']} "
                    f"(+{tb['boost']}, {tb['samples']} samples)"
                )
            print(f"Social queue: {len(social_queue())}")
            try:
                from modules.Bolt_Voice import speak_result

                speak_result(
                    f"Manager status: {len(list_items())} catalog items, "
                    f"{summary['total']} storefront, "
                    f"{ship['total']} shipped reviews, "
                    f"{sp['active']} active sponsors, "
                    f"{len(social_queue())} in social queue."
                )
            except Exception:
                pass
        elif args.cmd == "store-add":
            item = store_add(args.name, args.asin, args.category, args.notes)
            print(json.dumps(item, indent=2))
        elif args.cmd == "store-list":
            for s in store_list():
                print(f"  - {s.get('name')} asin={s.get('asin')} {s.get('affiliate_link')}")
        elif args.cmd == "store-feature-next":
            print(json.dumps(store_feature_next(), indent=2))
        elif args.cmd == "social-status":
            data = social_status()
            for name, meta in data.get("platforms", {}).items():
                print(f"  {name}: {meta.get('handle')} [{meta.get('status')}] mode={meta.get('upload_mode')}")
            print(f"  require_approval={data.get('require_approval', True)}")
        elif args.cmd == "social-package":
            plats = [p.strip() for p in args.platforms.split(",") if p.strip()]
            entry = social_package(args.name, plats)
            print(json.dumps(entry, indent=2))
            print("\nStatus: awaiting_approval (will not post automatically)")
        elif args.cmd == "social-queue":
            for q in social_queue():
                print(f"  {q.get('id')} {q.get('item')} [{q.get('status')}]")
        elif args.cmd == "sponsors-find":
            for s in sponsors_find(args.lane, args.limit):
                print(f"  {s['name']} fit={s.get('fit')} lanes={s.get('lanes')} — {s.get('why')}")
        elif args.cmd == "sponsors-pitch":
            pitch = sponsors_pitch(args.name)
            print(f"Subject: {pitch['subject']}\n")
            print(pitch["body"])
        elif args.cmd == "sponsors-log":
            row = sponsors_log(args.name, args.status, args.note)
            print(json.dumps(row, indent=2))
        elif args.cmd == "sponsors-next":
            found = sponsors_find(limit=1)
            if found:
                print(f"Next: {found[0]['name']} — {found[0].get('why')}")
                print(f"Run: bolt sponsors pitch \"{found[0]['name']}\"")
            else:
                print("No prospects. Add with: bolt sponsors log NAME --status prospect")
        elif args.cmd == "business-lesson":
            print(business_lesson())
        elif args.cmd == "business-next":
            for a in next_actions():
                if a["type"] == "business":
                    print(f"{a['title']}\n{a['why']}\n{a['command']}")
                    break
        elif args.cmd == "advance-next":
            step = advance_next()
            print(f"{step['title']}\n{step['why']}\n{step['command']}")
        elif args.cmd == "morning":
            # morning() prints the brief + speaks (wait=True) when not --quiet
            morning(speak_aloud=not args.quiet)
        else:
            parser.print_help()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # Allow `python -m modules.Content_Manager` from Core/
    if str(REPO_ROOT / "Core") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "Core"))
    raise SystemExit(main())
