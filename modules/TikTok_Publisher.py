#!/usr/bin/env python3
"""
modules/TikTok_Publisher.py — Upload clips to TikTok
=====================================================
Implements the TikTok Content Posting API v2 (file upload flow):
  1. Init upload → get upload_url + publish_id
  2. Chunk upload (64 MB max per chunk)
  3. Poll status until published or failed

Requires TIKTOK_ACCESS_TOKEN in .env.
"""

import os
import time
import math
import json
import mimetypes
from pathlib import Path
from typing import Optional, List

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from modules.notifier import notify, notify_post
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")
    def notify_post(title, platform, status, url=None, reason=None):
        print(f"  📤  [{platform}] {status}: {title}")
        if url:
            print(f"      {url}")

TIKTOK_INIT_URL   = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
CHUNK_SIZE        = 64 * 1024 * 1024  # 64 MB


class TikTokPublisher:
    """Upload and publish a video to TikTok via the Content Posting API."""

    def __init__(self, access_token: Optional[str] = None):
        self.token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
        if not self.token:
            notify(
                "TikTok access token not configured",
                level="warning",
                reason="Add TIKTOK_ACCESS_TOKEN=... to .env. Get a token from "
                       "developers.tiktok.com → your app → Content Posting API."
            )

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def publish(
        self,
        video_path: str,
        title: str,
        hashtags: Optional[List[str]] = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
        disable_comment: bool = False,
        disable_duet: bool = False,
        disable_stitch: bool = False,
    ) -> dict:
        """
        Full publish flow: init → chunk upload → poll.

        Returns dict with keys: success (bool), publish_id, url, error.
        """
        if not requests:
            return {"success": False, "error": "requests library not installed — pip install requests"}
        if not self.token:
            return {"success": False, "error": "TIKTOK_ACCESS_TOKEN not set"}

        path = Path(video_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {video_path}"}

        file_size = path.stat().st_size
        chunk_count = math.ceil(file_size / CHUNK_SIZE)

        # Combine title + hashtags into caption
        tags_str = " ".join(hashtags or [])
        caption = f"{title} {tags_str}".strip()[:2200]  # TikTok cap

        notify(
            f"Publishing to TikTok: {path.name}",
            level="info",
            reason=f"File size: {file_size / 1_048_576:.1f} MB | "
                   f"Chunks: {chunk_count} | Caption: {caption[:60]}…"
        )

        # ── Step 1: Init upload ──────────────────────────────────────────────
        notify("Step 1/3 — Initialising upload with TikTok API…", level="info",
               reason="The init call reserves a slot on TikTok's servers and returns "
                      "an upload_url + publish_id. The publish_id is used to poll "
                      "upload status later.")
        init_payload = {
            "post_info": {
                "title": caption,
                "privacy_level": privacy,
                "disable_comment": disable_comment,
                "disable_duet": disable_duet,
                "disable_stitch": disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": min(CHUNK_SIZE, file_size),
                "total_chunk_count": chunk_count,
            },
        }

        try:
            resp = requests.post(TIKTOK_INIT_URL, headers=self._headers,
                                 json=init_payload, timeout=30)
            data = resp.json()
        except Exception as exc:
            notify(f"Init request failed: {exc}", level="error")
            return {"success": False, "error": str(exc)}

        if resp.status_code != 200 or data.get("error", {}).get("code") != "ok":
            err = data.get("error", {})
            notify(f"TikTok init error: {err.get('message', 'unknown')}", level="error",
                   reason="Common causes: expired access token, missing Content Posting "
                          "API scope, or video duration outside 3s–60min limit.")
            return {"success": False, "error": err.get("message", "init failed")}

        upload_url = data["data"]["upload_url"]
        publish_id = data["data"]["publish_id"]
        notify(f"Upload initialised — publish_id: {publish_id}", level="success")

        # ── Step 2: Chunk upload ─────────────────────────────────────────────
        notify(f"Step 2/3 — Uploading {chunk_count} chunk(s)…", level="info",
               reason="Chunks are sent with Content-Range headers. TikTok reassembles "
                      "them server-side. Using 64 MB chunks for reliability on slow connections.")
        ok, err = self._upload_chunks(path, upload_url, file_size, chunk_count)
        if not ok:
            notify(f"Chunk upload failed: {err}", level="error")
            return {"success": False, "publish_id": publish_id, "error": err}

        notify("Chunks uploaded successfully ✓", level="success")

        # ── Step 3: Poll status ──────────────────────────────────────────────
        notify("Step 3/3 — Polling publish status…", level="info",
               reason="TikTok processes the video server-side (transcoding, moderation). "
                      "This usually takes 15-60 seconds. Bolt polls every 10s up to 5 minutes.")
        result = self._poll_status(publish_id, title)
        return result

    def _upload_chunks(self, path: Path, upload_url: str,
                       file_size: int, chunk_count: int) -> tuple:
        try:
            with open(path, "rb") as f:
                for i in range(chunk_count):
                    start = i * CHUNK_SIZE
                    chunk_data = f.read(CHUNK_SIZE)
                    end = start + len(chunk_data) - 1

                    headers = {
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Length": str(len(chunk_data)),
                    }
                    resp = requests.put(upload_url, headers=headers,
                                        data=chunk_data, timeout=300)
                    if resp.status_code not in (200, 201, 206):
                        return False, f"Chunk {i+1} HTTP {resp.status_code}: {resp.text[:200]}"
                    notify(f"  Chunk {i+1}/{chunk_count} uploaded ✓", level="info")
            return True, None
        except Exception as exc:
            return False, str(exc)

    def _poll_status(self, publish_id: str, title: str,
                     max_wait: int = 300) -> dict:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                resp = requests.post(
                    TIKTOK_STATUS_URL,
                    headers=self._headers,
                    json={"publish_id": publish_id},
                    timeout=15,
                )
                data = resp.json()
            except Exception as exc:
                notify(f"Status poll error: {exc}", level="warning")
                time.sleep(10)
                continue

            status = data.get("data", {}).get("status", "UNKNOWN")
            notify(f"  TikTok status: {status}", level="info")

            if status == "PUBLISH_COMPLETE":
                share_url = data.get("data", {}).get("publicaly_available_post_id", [])
                url = f"https://www.tiktok.com/video/{share_url[0]}" if share_url else None
                notify_post(title, "TikTok", "published", url=url,
                            reason="Video is live and publicly visible. "
                                   "Engagement metrics will be available in ~1 hour.")
                return {"success": True, "publish_id": publish_id, "url": url}

            if status in ("FAILED", "REJECTED"):
                reason = data.get("data", {}).get("fail_reason", "unknown")
                notify_post(title, "TikTok", f"failed ({reason})",
                            reason="TikTok rejected the video. Common reasons: "
                                   "community guideline violation, duplicate content, "
                                   "or audio copyright match.")
                return {"success": False, "publish_id": publish_id,
                        "error": f"TikTok {status}: {reason}"}

            time.sleep(10)

        notify(f"TikTok publish timed out after {max_wait}s", level="error",
               reason="The video may still publish — check your TikTok app. "
                      "The publish_id is saved so you can query status manually.")
        return {"success": False, "publish_id": publish_id, "error": "timeout"}


# Module-level convenience function
def publish_clip(
    video_path: str,
    title: str,
    hashtags: Optional[List[str]] = None,
    access_token: Optional[str] = None,
    **kwargs,
) -> dict:
    """One-shot publish. Creates a TikTokPublisher and calls publish()."""
    publisher = TikTokPublisher(access_token)
    return publisher.publish(video_path, title, hashtags=hashtags, **kwargs)
