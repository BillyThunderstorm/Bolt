#!/usr/bin/env python3
"""
modules/TikTok_Analytics.py — Pull real post stats from the TikTok Open API
=============================================================================
Uses the Login Kit / Display API endpoints (scope: video.list):

  POST /v2/video/list/   — paginated list of the authorized user's public videos
  POST /v2/video/query/  — detail + metrics for specific video IDs

Returned fields include view_count, like_count, comment_count, share_count.

Requires:
  - TIKTOK_ACCESS_TOKEN in .env (refreshable via TikTok_Auth)
  - Scope ``video.list`` granted on the token
    (re-run: python3 scripts/get_tiktok_token.py --scopes
     "user.info.basic,video.list,video.publish,video.upload")

This module does NOT write performance logs — see Performance_Sync for that.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional

LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"

# Metrics + identity fields for the learning loop / dashboard.
DEFAULT_FIELDS = (
    "id,create_time,title,video_description,duration,share_url,"
    "view_count,like_count,comment_count,share_count,cover_image_url"
)


@dataclass
class TikTokVideoStats:
    """Normalized stats for one TikTok video."""

    id: str
    title: str = ""
    video_description: str = ""
    create_time: int = 0  # unix seconds
    duration: float = 0.0
    share_url: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    cover_image_url: str = ""

    @classmethod
    def from_api(cls, raw: Dict[str, Any]) -> "TikTokVideoStats":
        return cls(
            id=str(raw.get("id") or ""),
            title=str(raw.get("title") or ""),
            video_description=str(raw.get("video_description") or ""),
            create_time=int(raw.get("create_time") or 0),
            duration=float(raw.get("duration") or 0),
            share_url=str(raw.get("share_url") or ""),
            view_count=int(raw.get("view_count") or 0),
            like_count=int(raw.get("like_count") or 0),
            comment_count=int(raw.get("comment_count") or 0),
            share_count=int(raw.get("share_count") or 0),
            cover_image_url=str(raw.get("cover_image_url") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TikTokAnalyticsError(RuntimeError):
    """Raised when the TikTok Analytics API returns an error or is unusable."""


class TikTokAnalytics:
    """Thin client for TikTok video list + query endpoints."""

    def __init__(self, access_token: Optional[str] = None):
        self.token = (access_token or self._load_token() or "").strip()
        if not self.token:
            raise TikTokAnalyticsError(
                "No TikTok access token. Run:\n"
                "  python3 scripts/get_tiktok_token.py --scopes "
                '"user.info.basic,video.list,video.publish,video.upload"\n'
                "and ensure video.list is approved on your TikTok developer app."
            )

    @staticmethod
    def _load_token() -> Optional[str]:
        try:
            from modules.TikTok_Auth import ensure_access_token

            return ensure_access_token()
        except Exception:
            import os

            return os.getenv("TIKTOK_ACCESS_TOKEN") or None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _post(
        self,
        base_url: str,
        body: Dict[str, Any],
        fields: str = DEFAULT_FIELDS,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        url = f"{base_url}?{urllib.parse.urlencode({'fields': fields})}"
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise TikTokAnalyticsError(
                f"TikTok API HTTP {exc.code}: {body_text[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TikTokAnalyticsError(f"TikTok API network error: {exc}") from exc

        err = data.get("error") or {}
        code = err.get("code", "ok")
        if code not in ("ok", "", None):
            msg = err.get("message") or code
            raise TikTokAnalyticsError(
                f"TikTok API error ({code}): {msg}. "
                "If this mentions scope, re-authorize with video.list."
            )
        return data

    def list_page(
        self,
        max_count: int = 20,
        cursor: Optional[int] = None,
        fields: str = DEFAULT_FIELDS,
    ) -> Dict[str, Any]:
        """Fetch one page of the user's public videos.

        Returns the raw ``data`` object: {videos, cursor, has_more}.
        """
        body: Dict[str, Any] = {"max_count": max(1, min(int(max_count), 20))}
        if cursor is not None:
            body["cursor"] = int(cursor)
        raw = self._post(LIST_URL, body, fields=fields)
        return raw.get("data") or {}

    def list_videos(
        self,
        limit: int = 100,
        max_pages: int = 10,
        fields: str = DEFAULT_FIELDS,
    ) -> List[TikTokVideoStats]:
        """Paginate through the user's videos up to ``limit`` items."""
        out: List[TikTokVideoStats] = []
        cursor: Optional[int] = None
        pages = 0
        while pages < max_pages and len(out) < limit:
            page_size = min(20, limit - len(out))
            data = self.list_page(max_count=page_size, cursor=cursor, fields=fields)
            videos = data.get("videos") or []
            for raw in videos:
                stats = TikTokVideoStats.from_api(raw)
                if stats.id:
                    out.append(stats)
                if len(out) >= limit:
                    break
            pages += 1
            if not data.get("has_more"):
                break
            next_cursor = data.get("cursor")
            if next_cursor is None:
                break
            cursor = int(next_cursor)
        return out

    def query_videos(
        self,
        video_ids: Iterable[str],
        fields: str = DEFAULT_FIELDS,
    ) -> List[TikTokVideoStats]:
        """Fetch metrics for specific video IDs (must belong to the user)."""
        ids = [str(v) for v in video_ids if v]
        if not ids:
            return []
        # API accepts up to 20 IDs per request.
        out: List[TikTokVideoStats] = []
        for i in range(0, len(ids), 20):
            chunk = ids[i : i + 20]
            raw = self._post(
                QUERY_URL,
                {"filters": {"video_ids": chunk}},
                fields=fields,
            )
            data = raw.get("data") or {}
            for item in data.get("videos") or []:
                stats = TikTokVideoStats.from_api(item)
                if stats.id:
                    out.append(stats)
        return out


def fetch_recent_video_stats(
    limit: int = 50,
    access_token: Optional[str] = None,
) -> List[TikTokVideoStats]:
    """Convenience: list recent videos with engagement metrics."""
    client = TikTokAnalytics(access_token=access_token)
    return client.list_videos(limit=limit)


if __name__ == "__main__":
    import sys

    try:
        videos = fetch_recent_video_stats(limit=10)
    except TikTokAnalyticsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not videos:
        print("No public videos returned (empty account, private-only, or scope issue).")
        sys.exit(0)

    print(f"{'ID':<22} {'Views':>8} {'Likes':>7}  Title")
    print("-" * 72)
    for v in videos:
        title = (v.title or v.video_description or "")[:40]
        print(f"{v.id:<22} {v.view_count:>8,} {v.like_count:>7,}  {title}")
