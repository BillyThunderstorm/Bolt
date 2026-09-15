"""
Twitch_Stats.py — Bolt Twitch API module
=========================================
Fetches live channel data from Twitch using the Helix API.

What it pulls:
  - Channel info (title, game, tags)
  - Follower count
  - Stream status (live/offline, viewer count, uptime)
  - Recent clips (top 5 by views)

Why it works this way:
  Twitch's API uses a two-step auth system:
    1. Client ID  — identifies YOUR app (like a username for Bolt)
    2. App Access Token — a temporary password Twitch gives you after verifying
       your Client ID + Secret. It expires after ~60 days, so we auto-refresh it.

  You do NOT need to log in as a user for read-only stats like follower count
  or stream status. That only requires the App Access Token (no OAuth needed).

Usage:
  from modules.Twitch_Stats import TwitchStats
  stats = TwitchStats()
  data = stats.get_all()
  print(data)
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_BASE = "https://api.twitch.tv/helix"
TOKEN_CACHE_FILE = Path(__file__).resolve().parents[2] / "Data" / "twitch_stats_token_cache.json"




# ── Tool / readiness helpers (never raise) ─────────────────────────────────────


def find_yt_dlp() -> Optional[str]:
    """
    Resolve yt-dlp: venv sibling of sys.executable first, then PATH.
    Returns absolute path or bare command name found on PATH, else None.
    """
    import shutil
    import sys

    venv_bin = Path(sys.executable).resolve().parent / "yt-dlp"
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    which = shutil.which("yt-dlp")
    return which


def find_ffmpeg() -> Optional[str]:
    """
    Resolve a working ffmpeg binary (never raises).

    PATH's ``ffmpeg`` can exist and still fail to launch (broken Homebrew
    dylib). Prefer ``FFmpeg_Bin`` (ffmpeg-full, then a binary that answers
    ``-version``). Returns None when nothing actually starts.
    """
    try:
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        import shutil

        which = shutil.which("ffmpeg")
        return which


def _env_creds() -> Dict[str, str]:
    return {
        "client_id": (os.getenv("TWITCH_CLIENT_ID", "") or "").strip(),
        "client_secret": (os.getenv("TWITCH_CLIENT_SECRET", "") or "").strip(),
        "channel": (os.getenv("TWITCH_CHANNEL", "") or "").strip().lower(),
    }


def status(*, probe: bool = False, channel: Optional[str] = None) -> Dict[str, Any]:
    """
    VOD / highlight-reel surface readiness. Never raises; never hangs.
    ready = Twitch client id+secret + channel present (tools ready for list/download).
    Helix reachability only checked when probe=True (informational if ready).
    """
    env = _env_creds()
    ch = (channel or env["channel"] or "").strip().lower()
    client_id_set = bool(env["client_id"])
    client_secret_set = bool(env["client_secret"])
    channel_set = bool(ch)
    yt = find_yt_dlp()
    ff = find_ffmpeg()

    ready = client_id_set and client_secret_set and channel_set

    info: Dict[str, Any] = {
        "ready": ready,
        "client_id_set": client_id_set,
        "client_secret_set": client_secret_set,
        "channel_set": channel_set,
        "channel": ch or None,
        "yt_dlp_found": bool(yt),
        "yt_dlp_path": yt,
        "ffmpeg_found": bool(ff),
        "ffmpeg_path": ff,
        "hint": "",
    }

    if not client_id_set or not client_secret_set:
        missing = []
        if not client_id_set:
            missing.append("TWITCH_CLIENT_ID")
        if not client_secret_set:
            missing.append("TWITCH_CLIENT_SECRET")
        info["hint"] = (
            "VOD unavailable: set "
            + " + ".join(missing)
            + " in .env (https://dev.twitch.tv/console). "
            "Also TWITCH_CHANNEL. yt-dlp optional on PATH for full VOD download."
        )
    elif not channel_set:
        info["hint"] = (
            "VOD unavailable: set TWITCH_CHANNEL in .env "
            "(channel login, e.g. thunderstormbilly)."
        )
    elif not yt:
        info["hint"] = (
            "Creds ready for Helix list; yt-dlp not found in venv or PATH "
            "(brew install yt-dlp or pip install yt-dlp). "
            "Sample downloads via ffmpeg still need ffmpeg. Try: bolt vods status --probe"
        )
    elif not ff:
        info["hint"] = (
            "Creds + yt-dlp ready; no working ffmpeg "
            "(PATH ffmpeg is often a broken Homebrew dylib). "
            "Need ffmpeg-full or BOLT_FFMPEG for samples. "
            "Try: brew install ffmpeg-full   or   bolt vods status --probe"
        )
    else:
        info["hint"] = (
            f"Configured for #{ch}. List/download: bolt vods / bolt auto_clip_twitch. "
            "Highlight reel: bolt highlights (needs media/clips/). "
            "Try: bolt vods status --probe"
        )

    if probe:
        info["probe_ok"] = False
        info["probe_detail"] = ""
        if not ready:
            info["probe_detail"] = info["hint"] or "VOD unavailable: missing creds/channel"
        else:
            try:
                ts, err = TwitchStats.try_create(channel=ch)
                if ts is None:
                    info["probe_detail"] = f"VOD unavailable: {err}"
                else:
                    user = ts.get_user()
                    if "error" in user:
                        info["probe_detail"] = f"VOD unavailable: {user['error']}"
                    else:
                        info["probe_ok"] = True
                        info["probe_detail"] = (
                            f"ok — Helix reachable for "
                            f"{user.get('display_name', ch)} (id={user.get('id')})"
                        )
                        info["hint"] = info["probe_detail"]
            except Exception as exc:
                info["probe_detail"] = f"VOD unavailable: Helix probe failed ({exc})"

    return info


# ── Main class ─────────────────────────────────────────────────────────────────


class TwitchStats:
    """
    Connects to the Twitch Helix API and fetches stats for a given channel.

    All methods return plain dicts so they're easy to display or save to JSON.
    """

    def __init__(self, channel: str = None):
        self.client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
        self.channel = (
            (channel or os.getenv("TWITCH_CHANNEL", "BillyandRandyGaming"))
            .strip()
            .lower()
        )
        self._token = None
        self._token_expiry = 0

        if not self.client_id:
            raise EnvironmentError(
                "TWITCH_CLIENT_ID is not set in your .env file.\n"
                "Add: TWITCH_CLIENT_ID=your_client_id_here"
            )
        if not self.client_secret:
            raise EnvironmentError(
                "TWITCH_CLIENT_SECRET is not set in your .env file.\n"
                "Get it from: https://dev.twitch.tv/console → Your App → Manage → Client Secret\n"
                "Add: TWITCH_CLIENT_SECRET=your_secret_here"
            )

    @classmethod
    def try_create(
        cls, channel: str = None
    ) -> Tuple[Optional["TwitchStats"], Optional[str]]:
        """
        Soft-fail constructor for status / CLI paths.
        Returns (instance, None) on success, or (None, reason) without raising.
        """
        try:
            return cls(channel=channel), None
        except EnvironmentError as e:
            msg = str(e).split("\n", 1)[0].strip() or str(e)
            return None, msg
        except Exception as e:
            return None, str(e)

    # ── Token management ───────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """
        Returns a valid App Access Token.
        Loads from cache if still valid, otherwise fetches a fresh one from Twitch.

        Why caching? Twitch rate-limits token requests. Fetching a new token
        every time the script runs would eventually get you blocked.
        """
        now = time.time()

        # Try loading from cache first
        if TOKEN_CACHE_FILE.exists():
            try:
                cache = json.loads(TOKEN_CACHE_FILE.read_text())
                if cache.get("expires_at", 0) > now + 300:  # 5-min buffer
                    return cache["access_token"]
            except Exception:
                pass  # Cache corrupted — just fetch a new token

        # Fetch fresh token from Twitch
        resp = requests.post(
            TWITCH_AUTH_URL,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token = data["access_token"]
        expires_at = now + data.get("expires_in", 3600)

        # Save to cache
        TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_FILE.write_text(
            json.dumps(
                {
                    "access_token": token,
                    "expires_at": expires_at,
                }
            )
        )

        return token

    def _headers(self) -> dict:
        """Auth headers required for every Twitch API call."""
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self._get_token()}",
        }

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make a GET request to the Twitch Helix API."""
        url = f"{TWITCH_API_BASE}/{endpoint}"
        resp = requests.get(
            url, headers=self._headers(), params=params or {}, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    # ── Data fetchers ──────────────────────────────────────────────────────────

    def get_user(self) -> dict:
        """
        Fetch basic user/channel info.
        Returns: id, login, display_name, description, profile_image_url, view_count
        """
        data = self._get("users", {"login": self.channel})
        users = data.get("data", [])
        if not users:
            return {"error": f"Channel '{self.channel}' not found on Twitch."}
        return users[0]

    def get_follower_count(self, broadcaster_id: str) -> int:
        """
        Fetch total follower count for a channel.
        Requires broadcaster_id (from get_user).
        """
        try:
            data = self._get("channels/followers", {"broadcaster_id": broadcaster_id})
            return data.get("total", 0)
        except Exception:
            return -1  # API may require user OAuth for exact count on some channels

    def get_stream_status(self, user_id: str) -> dict:
        """
        Check if the channel is currently live.
        Returns stream info if live, or {"live": False} if offline.
        """
        data = self._get("streams", {"user_id": user_id})
        streams = data.get("data", [])

        if not streams:
            return {"live": False, "message": "Channel is offline."}

        stream = streams[0]
        started_at = stream.get("started_at", "")

        # Calculate uptime
        uptime_str = ""
        if started_at:
            from datetime import datetime, timezone

            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - start
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            mins = rem // 60
            uptime_str = f"{hours}h {mins}m" if hours else f"{mins}m"

        return {
            "live": True,
            "title": stream.get("title", ""),
            "game_name": stream.get("game_name", ""),
            "viewer_count": stream.get("viewer_count", 0),
            "started_at": started_at,
            "uptime": uptime_str,
            "thumbnail_url": stream.get("thumbnail_url", "")
            .replace("{width}", "320")
            .replace("{height}", "180"),
        }

    def get_channel_info(self, broadcaster_id: str) -> dict:
        """
        Fetch current channel settings (title, game, tags).
        This is separate from stream status — exists even when offline.
        """
        data = self._get("channels", {"broadcaster_id": broadcaster_id})
        channels = data.get("data", [])
        if not channels:
            return {}
        ch = channels[0]
        return {
            "title": ch.get("title", ""),
            "game": ch.get("game_name", ""),
            "language": ch.get("broadcaster_language", ""),
            "tags": ch.get("tags", []),
        }

    def get_recent_clips(self, broadcaster_id: str, limit: int = 5) -> list:
        """
        Fetch the top clips by view count.
        Useful for seeing what content is performing best.
        """
        data = self._get(
            "clips",
            {
                "broadcaster_id": broadcaster_id,
                "first": limit,
            },
        )
        clips = data.get("data", [])
        return [
            {
                "title": c.get("title", ""),
                "view_count": c.get("view_count", 0),
                "created_at": c.get("created_at", "")[:10],  # date only
                "duration": round(c.get("duration", 0), 1),
                "url": c.get("url", ""),
            }
            for c in clips
        ]

    def get_videos(
        self,
        user_id: str,
        video_type: str = "archive",
        limit: int = 20,
    ) -> list:
        """
        List past broadcasts / saved highlights for a Twitch user.

        `video_type` is one of:
          - "archive"   : past broadcasts (auto-recorded VODs from live streams)
          - "highlight" : manually-saved highlight reels
          - "upload"    : manual uploads

        Returns a list of dicts:
          { id, title, created_at, duration, view_count, thumbnail_url, url }

        The Helix `videos` endpoint paginates with `after` cursors; this
        helper stops at `limit` results and doesn't follow pagination. If
        you need more, call repeatedly and pass the `cursor` from the
        response, or bump `limit`.
        """
        params: Dict = {
            "user_id": user_id,
            "type": video_type,
            "first": min(limit, 100),  # Helix hard limit
        }
        data = self._get("videos", params)
        items = data.get("data", [])
        out = []
        for v in items:
            vid = v.get("id", "")
            out.append(
                {
                    "id": vid,
                    "title": v.get("title", ""),
                    "created_at": v.get("created_at", "")[:10],
                    "duration": v.get("duration", ""),  # ISO 8601 string e.g. "2h13m47s"
                    "view_count": v.get("view_count", 0),
                    "thumbnail_url": v.get("thumbnail_url", ""),
                    "url": v.get("url", f"https://www.twitch.tv/videos/{vid}"),
                }
            )
        return out

    # ── All-in-one ─────────────────────────────────────────────────────────────

    def get_all(self) -> dict:
        """
        Fetch everything in one call and return a clean summary dict.
        This is what Bolt's dashboard and checklist use.
        """
        try:
            user = self.get_user()
            if "error" in user:
                return user

            broadcaster_id = user["id"]

            followers = self.get_follower_count(broadcaster_id)
            stream = self.get_stream_status(broadcaster_id)
            channel_info = self.get_channel_info(broadcaster_id)
            clips = self.get_recent_clips(broadcaster_id)

            return {
                "channel": self.channel,
                "display_name": user.get("display_name", self.channel),
                "followers": followers,
                "total_views": user.get("view_count", 0),
                "stream": stream,
                "channel_info": channel_info,
                "top_clips": clips,
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        except requests.HTTPError as e:
            return {
                "error": f"Twitch API error: {e.response.status_code} — {e.response.text}"
            }
        except Exception as e:
            return {"error": str(e)}

    def print_summary(self):
        """Print a human-readable summary to the terminal."""
        data = self.get_all()

        if "error" in data:
            print(f"\n❌ Twitch Stats Error: {data['error']}\n")
            return

        stream = data["stream"]
        ch = data["channel_info"]

        print("\n" + "═" * 50)
        print(f"  📺  {data['display_name']}  (@{data['channel']})")
        print("═" * 50)
        print(f"  Followers  : {data['followers']:,}")
        print(f"  Total Views: {data['total_views']:,}")
        print()

        if stream["live"]:
            print(
                f"  🔴 LIVE NOW  — {stream['viewer_count']:,} viewers  |  Up {stream['uptime']}"
            )
            print(f"  🎮 {stream['game_name']}")
            print(f"  📝 {stream['title']}")
        else:
            print(f"  ⚫ Offline")
            print(f"  📝 Last title: {ch.get('title', 'N/A')}")
            print(f"  🎮 Last game : {ch.get('game', 'N/A')}")

        print()
        if data["top_clips"]:
            print("  🏆 Top Clips:")
            for i, clip in enumerate(data["top_clips"], 1):
                print(
                    f"    {i}. {clip['title']} — {clip['view_count']:,} views ({clip['created_at']})"
                )

        print(f"\n  Updated: {data['fetched_at']}")
        print("═" * 50 + "\n")


# ── Run directly for quick test ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Twitch Helix stats / VOD readiness")
    parser.add_argument(
        "cmd",
        nargs="?",
        default="summary",
        help="summary (default) | status",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    if args.cmd in ("status", "vod-status", "vod_status"):
        info = status(probe=args.probe)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            for k in (
                "ready",
                "client_id_set",
                "client_secret_set",
                "channel_set",
                "channel",
                "yt_dlp_found",
                "yt_dlp_path",
                "ffmpeg_found",
                "ffmpeg_path",
                "hint",
            ):
                if k in info:
                    print(f"{k}: {info[k]}")
            if args.probe:
                print("probe_ok:", info.get("probe_ok"))
                print("probe_detail:", info.get("probe_detail"))
        raise SystemExit(0)

    stats, err = TwitchStats.try_create()
    if stats is None:
        print(f"VOD unavailable: {err}", file=sys.stderr)
        raise SystemExit(1)
    stats.print_summary()
