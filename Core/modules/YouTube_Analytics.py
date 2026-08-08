#!/usr/bin/env python3
"""
modules/YouTube_Analytics.py — Pull video / Shorts stats via YouTube Data API v3
=================================================================================
Reads the authorized channel's uploads and returns view/like/comment counts.

Flow:
  1. channels.list (mine=true) → uploads playlist id
  2. playlistItems.list → recent video IDs
  3. videos.list (part=snippet,statistics,contentDetails) → metrics

Requires:
  - YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in .env
  - OAuth token with scope youtube.readonly
    (python3 scripts/get_youtube_token.py)

This module does NOT write performance logs — see Performance_Sync.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class YouTubeVideoStats:
    """Normalized stats for one YouTube video or Short."""

    id: str
    title: str = ""
    description: str = ""
    published_at: str = ""  # ISO 8601 from API
    create_time: int = 0  # unix seconds (for matching)
    duration: str = ""  # ISO 8601 duration e.g. PT45S
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_url: str = ""
    channel_id: str = ""
    is_short: bool = False

    @classmethod
    def from_api(cls, raw: Dict[str, Any]) -> "YouTubeVideoStats":
        snippet = raw.get("snippet") or {}
        stats = raw.get("statistics") or {}
        details = raw.get("contentDetails") or {}
        vid = str(raw.get("id") or "")
        published = str(snippet.get("publishedAt") or "")
        create_time = 0
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                create_time = int(dt.timestamp())
            except Exception:
                create_time = 0
        duration = str(details.get("duration") or "")
        # Shorts are typically ≤60s vertical; ISO duration PT#S / PT#M#S
        is_short = _duration_seconds(duration) <= 60 if duration else False
        return cls(
            id=vid,
            title=str(snippet.get("title") or ""),
            description=str(snippet.get("description") or ""),
            published_at=published,
            create_time=create_time,
            duration=duration,
            view_count=int(stats.get("viewCount") or 0),
            like_count=int(stats.get("likeCount") or 0),
            comment_count=int(stats.get("commentCount") or 0),
            share_url=f"https://www.youtube.com/watch?v={vid}" if vid else "",
            channel_id=str(snippet.get("channelId") or ""),
            is_short=is_short,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _duration_seconds(iso_duration: str) -> int:
    """Parse a subset of ISO-8601 durations used by YouTube (PT#H#M#S)."""
    if not iso_duration or not iso_duration.startswith("PT"):
        return 0
    import re

    m = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        iso_duration,
    )
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


class YouTubeAnalyticsError(RuntimeError):
    """Raised when the YouTube Data API returns an error or is unusable."""


class YouTubeAnalytics:
    """Thin client for listing channel uploads with engagement metrics."""

    def __init__(self, access_token: Optional[str] = None):
        self.token = (access_token or self._load_token() or "").strip()
        if not self.token:
            raise YouTubeAnalyticsError(
                "No YouTube access token. Run:\n"
                "  python3 scripts/get_youtube_token.py\n"
                "after creating a Google Cloud OAuth client and enabling "
                "YouTube Data API v3."
            )

    @staticmethod
    def _load_token() -> Optional[str]:
        try:
            from modules.YouTube_Auth import ensure_access_token

            return ensure_access_token()
        except Exception:
            import os

            return os.getenv("YOUTUBE_ACCESS_TOKEN") or None

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _get(self, endpoint: str, params: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{API_BASE}/{endpoint}?{qs}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise YouTubeAnalyticsError(
                f"YouTube API HTTP {exc.code}: {body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise YouTubeAnalyticsError(f"YouTube API network error: {exc}") from exc

    def get_uploads_playlist_id(self) -> str:
        data = self._get(
            "channels",
            {"part": "contentDetails", "mine": "true"},
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeAnalyticsError(
                "No channel returned for this Google account. "
                "Sign in with the account that owns @SimplyBilly."
            )
        uploads = (
            (items[0].get("contentDetails") or {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads:
            raise YouTubeAnalyticsError("Channel has no uploads playlist id.")
        return str(uploads)

    def list_upload_ids(self, limit: int = 50) -> List[str]:
        """Return recent upload video IDs (newest first), up to ``limit``."""
        playlist_id = self.get_uploads_playlist_id()
        ids: List[str] = []
        page_token: Optional[str] = None
        while len(ids) < limit:
            page_size = min(50, limit - len(ids))
            params: Dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": page_size,
            }
            if page_token:
                params["pageToken"] = page_token
            data = self._get("playlistItems", params)
            for item in data.get("items") or []:
                vid = (item.get("contentDetails") or {}).get("videoId")
                if vid:
                    ids.append(str(vid))
                if len(ids) >= limit:
                    break
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids

    def query_videos(self, video_ids: List[str]) -> List[YouTubeVideoStats]:
        """Fetch snippet + statistics for up to 50 IDs per request."""
        out: List[YouTubeVideoStats] = []
        clean = [str(v) for v in video_ids if v]
        for i in range(0, len(clean), 50):
            chunk = clean[i : i + 50]
            data = self._get(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(chunk),
                },
            )
            for raw in data.get("items") or []:
                stats = YouTubeVideoStats.from_api(raw)
                if stats.id:
                    out.append(stats)
        return out

    def list_videos(
        self,
        limit: int = 50,
        shorts_only: bool = False,
    ) -> List[YouTubeVideoStats]:
        """List recent uploads with metrics.

        Parameters
        ----------
        shorts_only:
            If True, keep only videos with duration ≤ 60s (typical Shorts).
        """
        ids = self.list_upload_ids(limit=limit)
        videos = self.query_videos(ids)
        if shorts_only:
            videos = [v for v in videos if v.is_short]
        return videos


def fetch_recent_video_stats(
    limit: int = 50,
    shorts_only: bool = False,
    access_token: Optional[str] = None,
) -> List[YouTubeVideoStats]:
    client = YouTubeAnalytics(access_token=access_token)
    return client.list_videos(limit=limit, shorts_only=shorts_only)


if __name__ == "__main__":
    import sys

    try:
        videos = fetch_recent_video_stats(limit=10)
    except YouTubeAnalyticsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not videos:
        print("No uploads returned.")
        sys.exit(0)

    print(f"{'ID':<14} {'Views':>8} {'Likes':>7}  Title")
    print("-" * 72)
    for v in videos:
        flag = "S" if v.is_short else " "
        print(
            f"{v.id:<14} {v.view_count:>8,} {v.like_count:>7,} {flag} {v.title[:40]}"
        )
