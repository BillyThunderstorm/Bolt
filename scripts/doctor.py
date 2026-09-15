#!/usr/bin/env python3
"""Bolt connectivity doctor.

Reports what is live, mocked, on a stale path, or missing a key.
Canonical locations come from ``scripts/_paths.py``. Module constants are
compared against those locations so dual-folder leftovers after the July 2026
reorg show up as stale paths instead of silent misses.

Usage:
    bolt doctor
    bolt doctor --json
    python3 scripts/doctor.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    BOLT_BRAIN_FILE,
    CLIPS_DIR,
    CONFIG_FILE,
    CORE_DIR,
    DATA_DIR,
    DATA_ROOT,
    LOGS_DIR,
    MEMORY_DIR,
    MEMORY_HOT_FILE,
    RECORDINGS_DIR,
    REPO_ROOT,
    VERTICAL_CLIPS_DIR,
)

# Statuses that mean "this subsystem is not actually connected."
FAIL_STATUSES = frozenset({"stale_path", "missing_key", "missing_file", "broken"})
WARN_STATUSES = frozenset({"fallback", "mocked"})
OK_STATUSES = frozenset({"live", "disabled", "info"})

_LABELS = {
    "live": "live",
    "stale_path": "STALE",
    "missing_key": "KEY",
    "missing_file": "MISS",
    "broken": "BROKEN",
    "mocked": "MOCK",
    "fallback": "FALL",
    "disabled": "off",
    "info": "info",
}

_PLACEHOLDERS = {
    "",
    "your_key_here",
    "your_client_id_here",
    "your_client_secret_here",
    "your_obs_password_here",
    "your_discord_webhook_here",
    "sk_your_key_here",
}


@dataclass
class Check:
    subsystem: str
    name: str
    status: str
    detail: str
    expected: str = ""
    found: str = ""
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_path(found: Optional[Path], expected: Path) -> str:
    """Compare a module's path constant against the canonical location."""
    if found is None:
        return "missing_file" if not expected.exists() else "stale_path"
    try:
        found_r = found.resolve()
        expected_r = expected.resolve()
    except OSError:
        return "broken"
    if found_r == expected_r:
        return "live" if expected.exists() else "missing_file"
    if found.exists() or expected.exists():
        return "stale_path"
    return "missing_file"


def _rel(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except Exception:
        return str(path)
    return str(rel) if str(rel) != "." else "(repo root)"


def _key_set(value: Optional[str]) -> bool:
    raw = (value or "").strip()
    if not raw or raw in _PLACEHOLDERS:
        return False
    low = raw.lower()
    if low.startswith("todo") or "your_key" in low or low.startswith("sk_your"):
        return False
    return True


def _load_env() -> None:
    env_path = REPO_ROOT / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except Exception:
        pass
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _attr_path(module: Any, name: str) -> Optional[Path]:
    try:
        value = getattr(module, name)
    except Exception:
        return None
    if value is None:
        return None
    try:
        return Path(value)
    except TypeError:
        return None


def _check(
    subsystem: str,
    name: str,
    status: str,
    detail: str,
    *,
    expected: str = "",
    found: str = "",
    fix: str = "",
) -> Check:
    return Check(
        subsystem=subsystem,
        name=name,
        status=status,
        detail=detail,
        expected=expected,
        found=found,
        fix=fix,
    )


def _path_check(
    subsystem: str,
    name: str,
    found: Optional[Path],
    expected: Path,
    *,
    fix: str = "",
    live_detail: str = "",
) -> Check:
    status = classify_path(found, expected)
    if status == "live":
        detail = live_detail or f"{_rel(expected)} exists"
    elif status == "stale_path":
        detail = "module path does not match the canonical Data/Core location"
    elif status == "missing_file":
        detail = "canonical file is missing"
    else:
        detail = "path could not be resolved"
    return _check(
        subsystem,
        name,
        status,
        detail,
        expected=_rel(expected),
        found=_rel(found) if found is not None else "",
        fix=fix,
    )


def _ollama_probe(timeout: float = 2.0) -> dict[str, Any]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    host = os.getenv("OLLAMA_HOST", base.replace("/v1", "")).rstrip("/")
    url = f"{host}/api/tags"
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
        models = [
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
            if item
        ]
        return {"healthy": True, "url": url, "models": models}
    except Exception as exc:
        return {"healthy": False, "url": url, "models": [], "error": str(exc)[:160]}


def collect_paths() -> list[Check]:
    checks: list[Check] = []

    required = [
        ("config", CONFIG_FILE, "Core/config.json is the live config"),
        ("bolt brain", BOLT_BRAIN_FILE, "creator profile"),
        ("env file", REPO_ROOT / ".env", "API keys and tokens"),
        ("memory hot", MEMORY_HOT_FILE, "Data/MEMORY.md"),
        ("memory dir", MEMORY_DIR, "Data/memory/"),
        ("ready to post", DATA_ROOT / "ready_to_post.json", "post queue"),
        ("seen clips", DATA_ROOT / "seen_clips.json", "dedupe store"),
        ("clips dir", CLIPS_DIR, "media/clips"),
        ("vertical clips", VERTICAL_CLIPS_DIR, "media/vertical_clips"),
        ("recordings", RECORDINGS_DIR, "media/Recordings"),
        ("logs", LOGS_DIR, "logs/"),
    ]
    for name, path, detail in required:
        exists = path.exists()
        checks.append(
            _check(
                "paths",
                name,
                "live" if exists else "missing_file",
                detail if exists else f"missing {_rel(path)}",
                expected=_rel(path),
                found=_rel(path) if exists else "",
                fix="" if exists else f"create or restore {_rel(path)}",
            )
        )

    for name, leftover in (
        ("leftover Core/data", CORE_DIR / "data"),
        ("leftover Data/data", DATA_ROOT / "data"),
        ("leftover Core/logs", CORE_DIR / "logs"),
    ):
        if leftover.exists():
            checks.append(
                _check(
                    "paths",
                    name,
                    "stale_path",
                    "pre-reorg leftover tree came back",
                    found=_rel(leftover),
                    fix=f"move unique files into Data/ or logs/, then delete {_rel(leftover)}",
                )
            )

    try:
        from modules import Title_Generator as titles

        checks.append(
            _path_check(
                "paths",
                "title cache",
                _attr_path(titles, "TITLE_CACHE"),
                DATA_ROOT / "title_cache.json",
                fix="Title_Generator.TITLE_CACHE should be Data/title_cache.json",
                live_detail="title cache is in Data/",
            )
        )
        checks.append(
            _path_check(
                "paths",
                "title generator root",
                _attr_path(titles, "PROJECT_ROOT"),
                REPO_ROOT,
                live_detail="Title_Generator.PROJECT_ROOT is the repo root",
            )
        )
    except Exception as exc:
        checks.append(
            _check("paths", "title generator import", "broken", str(exc)[:160])
        )

    try:
        from modules import Think_Learn_Decide as tld

        checks.append(
            _path_check(
                "paths",
                "decision memory dir",
                _attr_path(tld, "MEMORY_DIR"),
                MEMORY_DIR,
                live_detail="Think_Learn_Decide.MEMORY_DIR is Data/memory/",
                fix="Think_Learn_Decide.MEMORY_DIR should be Data/memory/",
            )
        )
        checks.append(
            _path_check(
                "paths",
                "decision data dir",
                _attr_path(tld, "DATA_DIR"),
                DATA_ROOT,
                live_detail="Think_Learn_Decide.DATA_DIR is Data/",
            )
        )
    except Exception as exc:
        checks.append(
            _check("paths", "decision engine import", "broken", str(exc)[:160])
        )

    try:
        from modules import Peak_Hour_Notifier as peak

        checks.append(
            _path_check(
                "paths",
                "queue file",
                _attr_path(peak, "READY_FILE"),
                DATA_ROOT / "ready_to_post.json",
                live_detail="Peak_Hour_Notifier reads Data/ready_to_post.json",
            )
        )
    except Exception as exc:
        checks.append(_check("paths", "queue import", "broken", str(exc)[:160]))

    try:
        from modules import Memory_Index as mi

        checks.append(
            _path_check(
                "paths",
                "memory index dir",
                _attr_path(mi, "MEMORY_DIR"),
                MEMORY_DIR,
                live_detail="Memory_Index uses Data/memory/",
            )
        )
    except Exception as exc:
        checks.append(_check("paths", "memory index import", "broken", str(exc)[:160]))

    try:
        from modules import Bolt_Memory as bm

        checks.append(
            _path_check(
                "paths",
                "bolt memory file",
                _attr_path(bm, "MEMORY_FILE"),
                MEMORY_HOT_FILE,
                live_detail="Bolt_Memory reads Data/MEMORY.md",
            )
        )
    except Exception as exc:
        checks.append(_check("paths", "bolt memory import", "broken", str(exc)[:160]))

    layout_check = REPO_ROOT / "scripts" / "check_layout.py"
    if layout_check.exists():
        checks.append(
            _check(
                "paths",
                "check_layout.py",
                "info",
                "PARTIAL via bolt layout (report-only soft-fail; never moves; prefer this doctor for full audit).",
                found=_rel(layout_check),
            )
        )

    health_check = REPO_ROOT / "scripts" / "health_check.py"
    if health_check.exists():
        checks.append(
            _check(
                "paths",
                "health_check.py",
                "info",
                "PARTIAL via bolt health (post-reorg _paths); prefer this doctor for full audit.",
                found=_rel(health_check),
            )
        )

    clip_dedupe_script = REPO_ROOT / "scripts" / "clip_deduplicator.py"
    if clip_dedupe_script.exists():
        checks.append(
            _check(
                "paths",
                "clip_deduplicator.py",
                "info",
                "PARTIAL via bolt clip-dedupe (SHA256; fixed parents[3]; not pipeline pHash). Layout audit PARTIAL via bolt layout (report-only soft-fail; never moves).",
                found=_rel(clip_dedupe_script),
            )
        )

    return checks


def collect_titles(config: dict, ollama: dict[str, Any]) -> list[Check]:
    title_cfg = config.get("title_generation") or {}
    enabled = title_cfg.get("enabled")
    if enabled is None:
        enabled = bool(config.get("use_ai_titles"))
        tiers = config.get("quality_tiers") or {}
        if "use_ai_titles" in tiers:
            enabled = bool(tiers.get("use_ai_titles"))

    checks = [
        _check(
            "titles",
            "ai titles",
            "live" if enabled else "disabled",
            "use_ai_titles is on in Core/config.json"
            if enabled
            else "AI titles off; local templates only",
        )
    ]

    canonical = DATA_ROOT / "title_cache.json"
    active_cache = canonical
    if active_cache.exists():
        live_cache = _load_json(active_cache, {})
        n = len(live_cache) if isinstance(live_cache, dict) else 0
        checks.append(
            _check(
                "titles",
                "title cache",
                "live",
                f"{n} cached title set(s) at {_rel(active_cache)}",
                found=_rel(active_cache),
            )
        )
    else:
        checks.append(
            _check(
                "titles",
                "title cache",
                "info",
                "no title cache yet (first AI title run will create one)",
            )
        )

    has_xai = _key_set(os.getenv("XAI_API_KEY"))
    has_openai = _key_set(os.getenv("OPENAI_API_KEY"))
    if ollama.get("healthy"):
        llm_status, llm_detail = "live", "Ollama reachable for titles"
    elif has_xai:
        llm_status, llm_detail = "live", "Ollama down; xAI key present for paid titles"
    elif has_openai:
        llm_status, llm_detail = "fallback", "Ollama down; OpenAI key present"
    elif enabled:
        llm_status, llm_detail = (
            "fallback",
            "no title LLM reachable; pipeline uses local templates",
        )
    else:
        llm_status, llm_detail = "disabled", "AI titles off; templates only"
    checks.append(_check("titles", "title LLM", llm_status, llm_detail))

    checks.append(
        _check(
            "titles",
            "title trainer",
            "live",
            "bolt titles status|train|ab — learns from Data/performance_outcomes.jsonl "
            "into Data/viral_titles_model.json. Preview/edit still: bolt queue title. "
            "Performance: bolt stats / bolt log-perf (PARTIAL soft-fail).",
        )
    )
    return checks


def collect_llm(config: dict, ollama: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    mode = (os.getenv("BOLT_LLM_MODE") or (config.get("llm") or {}).get("mode") or "light")
    preferred = (
        os.getenv("BOLT_LLM_PROVIDER")
        or (config.get("llm") or {}).get("preferred")
        or "ollama"
    )
    checks.append(
        _check("llm", "budget mode", "live", f"BOLT_LLM_MODE={mode}  preferred={preferred}")
    )

    if ollama.get("healthy"):
        models = ollama.get("models") or []
        names = ", ".join(models[:6]) if models else "(no model names returned)"
        checks.append(
            _check(
                "llm",
                "ollama",
                "live",
                f"reachable at {ollama.get('url')}  models: {names}",
            )
        )
        wanted = {
            os.getenv("OLLAMA_MODEL") or os.getenv("BOLT_OLLAMA_MODEL") or "llama3.1:8b",
            os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text",
        }
        have = {m.split(":")[0] for m in models} | set(models)
        missing = [w for w in sorted(wanted) if w not in models and w.split(":")[0] not in have]
        if missing and models:
            checks.append(
                _check(
                    "llm",
                    "ollama models",
                    "missing_file",
                    "pull missing local models: " + ", ".join(missing),
                    fix="ollama pull " + " && ollama pull ".join(missing),
                )
            )
    else:
        checks.append(
            _check(
                "llm",
                "ollama",
                "missing_file",
                f"not reachable at {ollama.get('url')}",
                fix="start Ollama (ollama serve) or set OLLAMA_HOST",
            )
        )

    xai_on = _key_set(os.getenv("XAI_API_KEY"))
    checks.append(
        _check(
            "llm",
            "xAI key",
            "live" if xai_on else "disabled",
            "XAI_API_KEY set" if xai_on else "unset (optional unless you pass --paid / NEXUS_ALLOW_PAID)",
        )
    )
    openai_on = _key_set(os.getenv("OPENAI_API_KEY"))
    checks.append(
        _check(
            "llm",
            "OpenAI key",
            "live" if openai_on else "disabled",
            "OPENAI_API_KEY set" if openai_on else "unset (optional; titles/chat can stay local)",
        )
    )

    nexus_paid = (os.getenv("NEXUS_ALLOW_PAID") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    nexus_pref = os.getenv("NEXUS_PREFERRED") or "ollama"
    gemini = (os.getenv("NEXUS_USE_GEMINI") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if ollama.get("healthy") and nexus_pref == "ollama":
        nexus_status, nexus_detail = "live", f"Nexus preferred={nexus_pref} (free local)"
    elif nexus_paid and _key_set(os.getenv("XAI_API_KEY")):
        nexus_status, nexus_detail = (
            "live",
            f"Nexus preferred={nexus_pref}; paid Grok allowed",
        )
    elif ollama.get("healthy"):
        nexus_status, nexus_detail = "live", f"Nexus preferred={nexus_pref}; Ollama up"
    else:
        nexus_status, nexus_detail = (
            "fallback",
            "Nexus has no local LLM and paid Grok is off or unkeyed",
        )
    checks.append(_check("nexus", "routing", nexus_status, nexus_detail))
    checks.append(
        _check(
            "nexus",
            "gemini",
            "live" if gemini else "disabled",
            "NEXUS_USE_GEMINI is on" if gemini else "Gemini opt-in is off (default)",
        )
    )

    vector_dir = DATA_ROOT / "vector_db"
    if vector_dir.exists() and ollama.get("healthy"):
        checks.append(
            _check("nexus", "vector db", "live", f"{_rel(vector_dir)} present and Ollama is up")
        )
    elif vector_dir.exists():
        checks.append(
            _check(
                "nexus",
                "vector db",
                "fallback",
                f"{_rel(vector_dir)} exists but Ollama is down (embeddings will fail)",
                fix="start Ollama, then bolt reindex",
            )
        )
    else:
        checks.append(
            _check(
                "nexus",
                "vector db",
                "missing_file",
                "Data/vector_db/ missing",
                expected=_rel(vector_dir),
                fix="bolt reindex  (needs Ollama + nomic-embed-text)",
            )
        )
    return checks


def collect_queue() -> list[Check]:
    queue_path = DATA_ROOT / "ready_to_post.json"
    payload = _load_json(queue_path, None)
    if payload is None:
        return [
            _check(
                "queue",
                "ready_to_post.json",
                "missing_file",
                "post queue file is missing",
                expected=_rel(queue_path),
            )
        ]
    clips = payload.get("clips", payload) if isinstance(payload, dict) else payload
    if not isinstance(clips, list):
        clips = []
    ready = [
        c
        for c in clips
        if isinstance(c, dict)
        and c.get("status", "ready") == "ready"
        and not c.get("posted")
    ]
    ghosts = 0
    for clip in ready:
        path = clip.get("path") or clip.get("clip_path") or clip.get("file") or ""
        if path and not Path(path).exists() and not (VERTICAL_CLIPS_DIR / Path(path).name).exists():
            ghosts += 1
    detail = f"{len(clips)} row(s), {len(ready)} ready"
    if ghosts:
        detail += f", {ghosts} ghost file(s)"
    return [
        _check(
            "queue",
            "ready_to_post.json",
            "live" if not ghosts else "fallback",
            detail,
            found=_rel(queue_path),
            fix="bolt queue clean" if ghosts else "",
        )
    ]


def collect_social() -> list[Check]:
    checks: list[Check] = []
    try:
        from modules.Social_Stats import tiktok_ready, youtube_ready

        tiktok = tiktok_ready()
        youtube = youtube_ready()
    except Exception as exc:
        return [_check("social", "stats import", "broken", str(exc)[:160])]

    if tiktok.get("paused"):
        checks.append(
            _check(
                "social",
                "tiktok",
                "disabled",
                tiktok.get("next_step") or "TikTok API paused; bolt log-perf after posting",
            )
        )
    elif tiktok.get("ready"):
        checks.append(
            _check("social", "tiktok", "live", tiktok.get("next_step") or "TikTok token ready")
        )
    else:
        checks.append(
            _check(
                "social",
                "tiktok",
                "missing_key",
                tiktok.get("next_step") or "TikTok token missing",
                fix="bolt tiktok_token",
            )
        )

    if youtube.get("ready"):
        checks.append(
            _check(
                "social",
                "youtube",
                "live",
                youtube.get("next_step") or "YouTube token ready",
            )
        )
    else:
        checks.append(
            _check(
                "social",
                "youtube",
                "missing_key",
                youtube.get("next_step") or "YouTube token missing",
                fix="bolt youtube_token",
            )
        )
    return checks


def collect_integrations(config: dict) -> list[Check]:
    checks: list[Check] = []
    twitch_on = bool(config.get("use_twitch"))
    twitch_token = _key_set(os.getenv("TWITCH_BOT_TOKEN")) or _key_set(
        os.getenv("TWITCH_OAUTH_TOKEN")
    )
    twitch_channel = _key_set(os.getenv("TWITCH_CHANNEL"))
    if not twitch_on:
        checks.append(
            _check("integrations", "twitch", "disabled", "use_twitch is false in config")
        )
    elif twitch_token and twitch_channel:
        checks.append(_check("integrations", "twitch", "live", "Twitch chat token + channel set"))
    else:
        checks.append(
            _check(
                "integrations",
                "twitch",
                "missing_key",
                "use_twitch is on but TWITCH_CHANNEL / TWITCH_BOT_TOKEN missing",
                fix="bolt twitch_bot_token",
            )
        )

    obs_on = bool(config.get("use_obs_integration"))
    obs_password = _key_set(os.getenv("OBS_PASSWORD"))
    if not obs_on:
        checks.append(
            _check("integrations", "obs", "disabled", "use_obs_integration is false")
        )
    elif obs_password:
        checks.append(_check("integrations", "obs", "live", "OBS_PASSWORD set"))
    else:
        checks.append(
            _check(
                "integrations",
                "obs",
                "missing_key",
                "OBS integration on but OBS_PASSWORD missing",
                fix="set OBS_PASSWORD in .env",
            )
        )

    discord = _key_set(os.getenv("DISCORD_WEBHOOK_URL"))
    checks.append(
        _check(
            "integrations",
            "discord",
            "live" if discord else "disabled",
            "DISCORD_WEBHOOK_URL set" if discord else "unset (optional; bolt discord status — not a bot; preferred alerts: bolt alerts status)",
        )
    )

    learn_dir = REPO_ROOT / "Data" / "learning"
    learn_chapters = (
        [p for p in learn_dir.glob("*.md") if p.name != "_TEMPLATE.md"]
        if learn_dir.is_dir()
        else []
    )
    checks.append(
        _check(
            "integrations",
            "learning",
            "live" if learn_chapters else "disabled",
            (
                f"{len(learn_chapters)} chapter note(s); bolt learning status"
                if learn_chapters
                else "no Data/learning chapters (optional study log; bolt learning status)"
            ),
        )
    )

    req_doc = REPO_ROOT / "Docs" / "requirements" / "creator-domains-requirements.md"
    instr_doc = (
        REPO_ROOT / ".github" / "instructions" / "creator-domains.instructions.md"
    )
    domains_ok = (
        req_doc.is_file()
        and instr_doc.is_file()
        and req_doc.stat().st_size > 0
        and instr_doc.stat().st_size > 0
    )
    checks.append(
        _check(
            "integrations",
            "creator-domains",
            "live" if domains_ok else "disabled",
            (
                "requirements + instructions present; bolt domains status"
                if domains_ok
                else "missing creator-domains docs (optional spec browser; bolt domains status)"
            ),
        )
    )


    # Cloudflare Pages (William-specific PARTIAL — soft-fail via bolt pages)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Cloudflare_Pages import status as _pages_status

        _ps = _pages_status()
        pages_ready = bool(_ps.get("ready"))
        pages_detail = (
            f"wrangler+auth+path ready; bolt pages status"
            if pages_ready
            else (
                (_ps.get("hint") or "Pages unavailable: not ready")
                + " (optional William deploy; bolt pages status)"
            )
        )
        # Truncate long soft-fail hints for doctor table
        if len(pages_detail) > 160:
            pages_detail = pages_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "cloudflare-pages",
                "live" if pages_ready else "disabled",
                pages_detail,
            )
        )
    except Exception as _pages_exc:
        checks.append(
            _check(
                "integrations",
                "cloudflare-pages",
                "disabled",
                f"Pages unavailable: doctor import failed ({_pages_exc})",
            )
        )

    # License readiness (PARTIAL — soft-fail via bolt license)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Bolt_License import status as _license_status

        _ls = _license_status()
        lic_ready = bool(_ls.get("ready"))
        lic_detail = (
            f"LICENSE set ({_ls.get('detected_spdx') or 'custom'}); bolt license status"
            if lic_ready
            else (
                (_ls.get("hint") or "License unavailable: not ready")
                + " (optional; bolt license status)"
            )
        )
        if len(lic_detail) > 160:
            lic_detail = lic_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "license",
                "live" if lic_ready else "disabled",
                lic_detail,
            )
        )
    except Exception as _lic_exc:
        checks.append(
            _check(
                "integrations",
                "license",
                "disabled",
                f"License unavailable: doctor import failed ({_lic_exc})",
            )
        )


    # Mac .app assemble (PARTIAL — soft-fail via bolt mac-app)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Bolt_Mac_App import status as _macapp_status

        _ms = _macapp_status()
        mac_ready = bool(_ms.get("ready"))
        mac_detail = (
            f"dist/Bolt.app valid; bolt mac-app status"
            if mac_ready
            else (
                (_ms.get("hint") or "Mac app unavailable: not ready")
                + " (optional; bolt mac-app status)"
            )
        )
        if len(mac_detail) > 160:
            mac_detail = mac_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "mac-app",
                "live" if mac_ready else "disabled",
                mac_detail,
            )
        )
    except Exception as _mac_exc:
        checks.append(
            _check(
                "integrations",
                "mac-app",
                "disabled",
                f"Mac app unavailable: doctor import failed ({_mac_exc})",
            )
        )


    # Mac automation launchd/cron/Shortcuts (PARTIAL — soft-fail via bolt mac-auto)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Mac_Automation import status as _macauto_status

        _ma = _macauto_status()
        ma_ready = bool(_ma.get("ready"))
        ma_detail = (
            f"launchd/cron/shortcuts pieces ok; bolt mac-auto status"
            if ma_ready
            else (
                (_ma.get("hint") or _ma.get("error") or "Mac automation unavailable: not ready")
                + " (optional; bolt mac-auto status)"
            )
        )
        if len(ma_detail) > 160:
            ma_detail = ma_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "mac-automation",
                "live" if ma_ready else "disabled",
                ma_detail,
            )
        )
    except Exception as _ma_exc:
        checks.append(
            _check(
                "integrations",
                "mac-automation",
                "disabled",
                f"Mac automation unavailable: doctor import failed ({_ma_exc})",
            )
        )


    # Apple Reminders delivery (PARTIAL — soft-fail via bolt reminders)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Apple_Reminders import status as _reminders_status

        _rem = _reminders_status()
        rem_ready = bool(_rem.get("ready"))
        rem_detail = (
            f"Reminders tooling ok; bolt reminders status"
            if rem_ready
            else (
                (_rem.get("hint") or _rem.get("error") or "Reminders unavailable: not ready")
                + " (optional; bolt reminders status)"
            )
        )
        if len(rem_detail) > 160:
            rem_detail = rem_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "apple-reminders",
                "live" if rem_ready else "disabled",
                rem_detail,
            )
        )
    except Exception as _rem_exc:
        checks.append(
            _check(
                "integrations",
                "apple-reminders",
                "disabled",
                f"Reminders unavailable: doctor import failed ({_rem_exc})",
            )
        )

    # Photo / handwriting OCR (PARTIAL — soft-fail via bolt photo-ocr)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Photo_OCR import status as _photo_ocr_status

        _poc = _photo_ocr_status()
        poc_ready = bool(_poc.get("ready"))
        poc_detail = (
            f"Photo OCR tooling ok; bolt photo-ocr status"
            if poc_ready
            else (
                (_poc.get("hint") or _poc.get("error") or "Photo OCR unavailable: not ready")
                + " (optional; bolt photo-ocr status)"
            )
        )
        if len(poc_detail) > 160:
            poc_detail = poc_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "photo-ocr",
                "live" if poc_ready else "disabled",
                poc_detail,
            )
        )
    except Exception as _poc_exc:
        checks.append(
            _check(
                "integrations",
                "photo-ocr",
                "disabled",
                f"Photo OCR unavailable: doctor import failed ({_poc_exc})",
            )
        )

    # HandBrake clip compression (PARTIAL — soft-fail via bolt compress)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Video_Compress import status as _compress_status

        _vc = _compress_status()
        vc_ready = bool(_vc.get("ready"))
        vc_detail = (
            f"Compress tooling ok; bolt compress status"
            if vc_ready
            else (
                (_vc.get("hint") or _vc.get("error") or "Compress unavailable: not ready")
                + " (optional; bolt compress status)"
            )
        )
        if len(vc_detail) > 160:
            vc_detail = vc_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "video-compress",
                "live" if vc_ready else "disabled",
                vc_detail,
            )
        )
    except Exception as _vc_exc:
        checks.append(
            _check(
                "integrations",
                "video-compress",
                "disabled",
                f"Compress unavailable: doctor import failed ({_vc_exc})",
            )
        )




    # Performance baseline (PARTIAL — soft-fail via bolt performance)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Performance_Baseline import status as _baseline_status

        _bl = _baseline_status()
        bl_ready = bool(_bl.get("ready"))
        bl_detail = (
            f"Baseline tooling ok; bolt performance status"
            if bl_ready
            else (
                (_bl.get("hint") or _bl.get("error") or "Baseline unavailable: not ready")
                + " (optional; bolt performance status)"
            )
        )
        if len(bl_detail) > 160:
            bl_detail = bl_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "performance-baseline",
                "live" if bl_ready else "disabled",
                bl_detail,
            )
        )
    except Exception as _bl_exc:
        checks.append(
            _check(
                "integrations",
                "performance-baseline",
                "disabled",
                f"Baseline unavailable: doctor import failed ({_bl_exc})",
            )
        )




    # Weekly analysis (PARTIAL — soft-fail via bolt weekly)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Weekly_Analysis import status as _weekly_status

        _wk = _weekly_status()
        wk_ready = bool(_wk.get("ready"))
        wk_detail = (
            f"Weekly tooling ok; bolt weekly status"
            if wk_ready
            else (
                (_wk.get("hint") or _wk.get("error") or "Weekly unavailable: not ready")
                + " (optional; bolt weekly status)"
            )
        )
        if len(wk_detail) > 160:
            wk_detail = wk_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "weekly-analysis",
                "live" if wk_ready else "disabled",
                wk_detail,
            )
        )
    except Exception as _wk_exc:
        checks.append(
            _check(
                "integrations",
                "weekly-analysis",
                "disabled",
                f"Weekly unavailable: doctor import failed ({_wk_exc})",
            )
        )


    # Clip backlog score filter (PARTIAL — soft-fail via bolt filter-backlog)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Filter_Backlog import status as _filter_status

        _fb = _filter_status()
        fb_ready = bool(_fb.get("ready"))
        fb_detail = (
            f"Backlog filter tooling ok; bolt filter-backlog status"
            if fb_ready
            else (
                (_fb.get("hint") or _fb.get("error") or "Backlog unavailable: not ready")
                + " (optional; bolt filter-backlog status)"
            )
        )
        if len(fb_detail) > 160:
            fb_detail = fb_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "filter-backlog",
                "live" if fb_ready else "disabled",
                fb_detail,
            )
        )
    except Exception as _fb_exc:
        checks.append(
            _check(
                "integrations",
                "filter-backlog",
                "disabled",
                f"Backlog unavailable: doctor import failed ({_fb_exc})",
            )
        )

    # Local highlight reel stitch (PARTIAL — soft-fail via bolt make-highlights)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Make_Highlights import status as _mh_status

        _mh = _mh_status()
        mh_ready = bool(_mh.get("ready"))
        mh_detail = (
            f"Highlights tooling ok; bolt make-highlights status"
            if mh_ready
            else (
                (_mh.get("hint") or _mh.get("error") or "Highlights unavailable: not ready")
                + " (optional; bolt make-highlights status)"
            )
        )
        if len(mh_detail) > 160:
            mh_detail = mh_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "make-highlights",
                "live" if mh_ready else "disabled",
                mh_detail,
            )
        )
    except Exception as _mh_exc:
        checks.append(
            _check(
                "integrations",
                "make-highlights",
                "disabled",
                f"Highlights unavailable: doctor import failed ({_mh_exc})",
            )
        )

    # Vertical reprocess + multi-platform queue (PARTIAL — soft-fail via bolt reprocess)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Reprocess_Clips import status as _rp_status

        _rp = _rp_status()
        rp_ready = bool(_rp.get("ready"))
        rp_detail = (
            f"Reprocess tooling ok; bolt reprocess status"
            if rp_ready
            else (
                (_rp.get("hint") or _rp.get("error") or "Reprocess unavailable: not ready")
                + " (optional; bolt reprocess status)"
            )
        )
        if len(rp_detail) > 160:
            rp_detail = rp_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "reprocess",
                "live" if rp_ready else "disabled",
                rp_detail,
            )
        )
    except Exception as _rp_exc:
        checks.append(
            _check(
                "integrations",
                "reprocess",
                "disabled",
                f"Reprocess unavailable: doctor import failed ({_rp_exc})",
            )
        )

    # Lightweight health smoke (PARTIAL — soft-fail via bolt health; prefer this doctor)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Health_Check import status as _hc_status

        _hc = _hc_status()
        hc_ready = bool(_hc.get("ready"))
        hc_detail = (
            f"Health smoke ok; bolt health status (prefer bolt doctor)"
            if hc_ready
            else (
                (_hc.get("hint") or _hc.get("error") or "Health check unavailable: not ready")
                + " (optional; bolt health status)"
            )
        )
        if len(hc_detail) > 160:
            hc_detail = hc_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "health",
                "live" if hc_ready else "disabled",
                hc_detail,
            )
        )
    except Exception as _hc_exc:
        checks.append(
            _check(
                "integrations",
                "health",
                "disabled",
                f"Health check unavailable: doctor import failed ({_hc_exc})",
            )
        )






    # SMS/email notify CLI (PARTIAL — soft-fail via bolt send; prefers Bolt_Alerts)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Send_Notify import status as _send_status

        _sn = _send_status()
        sn_ready = bool(_sn.get("ready"))
        sn_detail = (
            "send/notify ok; bolt send status (Bolt_Alerts / send_notification)"
            if sn_ready
            else (
                (_sn.get("hint") or _sn.get("error") or "Notify unavailable: not ready")
                + " (optional; bolt send status)"
            )
        )
        if len(sn_detail) > 160:
            sn_detail = sn_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "send_notify",
                "live" if sn_ready else "disabled",
                sn_detail,
            )
        )
    except Exception as _sn_exc:
        checks.append(
            _check(
                "integrations",
                "send_notify",
                "disabled",
                f"Notify unavailable: doctor import failed ({_sn_exc})",
            )
        )

    # Local ICS calendar feeds (PARTIAL — soft-fail via bolt calendar; not bolt gcal)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.ICS_Calendar import status as _ics_status

        _ics = _ics_status()
        ics_ready = bool(_ics.get("ready"))
        ics_detail = (
            f"ICS calendar ok; bolt calendar status (Data/calendar/*.ics)"
            if ics_ready
            else (
                (_ics.get("hint") or _ics.get("error") or "Calendar unavailable: not ready")
                + " (optional; bolt calendar status)"
            )
        )
        if len(ics_detail) > 160:
            ics_detail = ics_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "ics_calendar",
                "live" if ics_ready else "disabled",
                ics_detail,
            )
        )
    except Exception as _ics_exc:
        checks.append(
            _check(
                "integrations",
                "ics_calendar",
                "disabled",
                f"Calendar unavailable: doctor import failed ({_ics_exc})",
            )
        )

    # Memory index rebuild CLI (PARTIAL — soft-fail via bolt refresh-memory; not briefing retrieve)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Refresh_Memory import status as _rm_status

        _rm = _rm_status()
        rm_ready = bool(_rm.get("ready"))
        rm_detail = (
            f"Memory refresh ok; bolt refresh-memory status (Data/memory_index.json)"
            if rm_ready
            else (
                (_rm.get("hint") or _rm.get("error") or "Memory refresh unavailable: not ready")
                + " (optional; bolt refresh-memory status)"
            )
        )
        if len(rm_detail) > 160:
            rm_detail = rm_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "refresh_memory",
                "live" if rm_ready else "disabled",
                rm_detail,
            )
        )
    except Exception as _rm_exc:
        checks.append(
            _check(
                "integrations",
                "refresh_memory",
                "disabled",
                f"Memory refresh unavailable: doctor import failed ({_rm_exc})",
            )
        )

    # Long-term memory store (PARTIAL — soft-fail via bolt memory; not refresh-memory / briefing retrieve)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Bolt_Memory import status as _bm_status

        _bm = _bm_status()
        bm_ready = bool(_bm.get("ready"))
        bm_detail = (
            "Bolt memory ok; bolt memory status (Data/MEMORY.md + memory dirs)"
            if bm_ready
            else (
                (_bm.get("hint") or _bm.get("error") or "Bolt memory unavailable: not ready")
                + " (optional; bolt memory status)"
            )
        )
        if len(bm_detail) > 160:
            bm_detail = bm_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "bolt_memory",
                "live" if bm_ready else "disabled",
                bm_detail,
            )
        )
    except Exception as _bm_exc:
        checks.append(
            _check(
                "integrations",
                "bolt_memory",
                "disabled",
                f"Bolt memory unavailable: doctor import failed ({_bm_exc})",
            )
        )

    # Folder watch CLI (PARTIAL — soft-fail via bolt watch; prefer bolt launch)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Folder_Watch import status as _fw_status

        _fw = _fw_status()
        fw_ready = bool(_fw.get("ready"))
        fw_detail = (
            f"Folder watch ok; bolt watch status (Data/processed_recordings.json)"
            if fw_ready
            else (
                (_fw.get("hint") or _fw.get("error") or "Watch unavailable: not ready")
                + " (optional; bolt watch status)"
            )
        )
        if len(fw_detail) > 160:
            fw_detail = fw_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "folder_watch",
                "live" if fw_ready else "disabled",
                fw_detail,
            )
        )
    except Exception as _fw_exc:
        checks.append(
            _check(
                "integrations",
                "folder_watch",
                "disabled",
                f"Watch unavailable: doctor import failed ({_fw_exc})",
            )
        )

    # OBS scene→config game tracker (PARTIAL — soft-fail via bolt obs-game; not bolt obs)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.OBS_Game_Tracker import status as _ogt_status

        _ogt = _ogt_status()
        ogt_ready = bool(_ogt.get("ready"))
        ogt_detail = (
            f"OBS game tracker ok; bolt obs-game status (Data/configs/scene_game_mapping.json)"
            if ogt_ready
            else (
                (_ogt.get("hint") or _ogt.get("error") or "Game tracker unavailable: not ready")
                + " (optional; bolt obs-game status)"
            )
        )
        if len(ogt_detail) > 160:
            ogt_detail = ogt_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "obs_game_tracker",
                "live" if ogt_ready else "disabled",
                ogt_detail,
            )
        )
    except Exception as _ogt_exc:
        checks.append(
            _check(
                "integrations",
                "obs_game_tracker",
                "disabled",
                f"Game tracker unavailable: doctor import failed ({_ogt_exc})",
            )
        )

    # Dictionary / spellcheck / thesaurus (READY — local spell via bolt word)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Word_Lookup import status as _word_status

        _wl = _word_status()
        wl_ready = bool(_wl.get("ready"))
        wl_detail = (
            f"Word lookup ok; bolt word status ({_wl.get('word_count') or 0} words)"
            if wl_ready
            else (
                (_wl.get("hint") or _wl.get("error") or "Word lookup unavailable: not ready")
                + " (optional; bolt word status)"
            )
        )
        if len(wl_detail) > 160:
            wl_detail = wl_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "word-lookup",
                "live" if wl_ready else "disabled",
                wl_detail,
            )
        )
    except Exception as _wl_exc:
        checks.append(
            _check(
                "integrations",
                "word-lookup",
                "disabled",
                f"Word lookup unavailable: doctor import failed ({_wl_exc})",
            )
        )

    # iCloud Drive multi-Mac sync (PARTIAL — soft-fail via bolt icloud; not bolt mac-auto)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.ICloud_Sync import status as _icl_status

        _icl = _icl_status()
        icl_ready = bool(_icl.get("ready"))
        icl_detail = (
            "iCloud sync ok; bolt icloud status (scripts/move_to_icloud.sh)"
            if icl_ready
            else (
                (_icl.get("hint") or _icl.get("error") or "iCloud unavailable: not ready")
                + " (optional; bolt icloud status)"
            )
        )
        if len(icl_detail) > 160:
            icl_detail = icl_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "icloud_sync",
                "live" if icl_ready else "disabled",
                icl_detail,
            )
        )
    except Exception as _icl_exc:
        checks.append(
            _check(
                "integrations",
                "icloud_sync",
                "disabled",
                f"iCloud unavailable: doctor import failed ({_icl_exc})",
            )
        )

    # Per-game sensitivity profiles (PARTIAL — soft-fail via bolt game-config; not bolt obs-game)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Game_Config import status as _gc_status

        _gc = _gc_status()
        gc_ready = bool(_gc.get("ready"))
        gc_detail = (
            "Game config ok; bolt game-config status "
            f"(builtin={_gc.get('builtin_profile_count')})"
            if gc_ready
            else (
                (_gc.get("hint") or _gc.get("error") or "Game config unavailable: not ready")
                + " (optional; bolt game-config status)"
            )
        )
        if len(gc_detail) > 160:
            gc_detail = gc_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "game_config",
                "live" if gc_ready else "disabled",
                gc_detail,
            )
        )
    except Exception as _gc_exc:
        checks.append(
            _check(
                "integrations",
                "game_config",
                "disabled",
                f"Game config unavailable: doctor import failed ({_gc_exc})",
            )
        )

    # Error recovery / quarantine (PARTIAL — soft-fail via bolt error-recovery; not discord/alerts)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Error_Recovery import status as _er_status

        _er = _er_status()
        er_ready = bool(_er.get("ready"))
        er_detail = (
            "Error recovery ok; bolt error-recovery status "
            f"(quarantine={_er.get('quarantine_count', 0)})"
            if er_ready
            else (
                (_er.get("hint") or _er.get("error") or "Error recovery unavailable: not ready")
                + " (optional; bolt error-recovery status)"
            )
        )
        if len(er_detail) > 160:
            er_detail = er_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "error_recovery",
                "live" if er_ready else "disabled",
                er_detail,
            )
        )
    except Exception as _er_exc:
        checks.append(
            _check(
                "integrations",
                "error_recovery",
                "disabled",
                f"Error recovery unavailable: doctor import failed ({_er_exc})",
            )
        )

    # Phase 4 semantic memory search (PARTIAL — soft-fail via bolt memsearch; not web search / LLM memory)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Memory_Search import status as _ms_status

        _ms = _ms_status()
        ms_ready = bool(_ms.get("ready"))
        ms_detail = (
            "Memory search ok; bolt memsearch status "
            f"(entries={_ms.get('index_entry_count', 0)})"
            if ms_ready
            else (
                (_ms.get("hint") or _ms.get("error") or "Memory search unavailable: not ready")
                + " (optional; bolt memsearch status)"
            )
        )
        if len(ms_detail) > 160:
            ms_detail = ms_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "memsearch",
                "live" if ms_ready else "disabled",
                ms_detail,
            )
        )
    except Exception as _ms_exc:
        checks.append(
            _check(
                "integrations",
                "memsearch",
                "disabled",
                f"Memory search unavailable: doctor import failed ({_ms_exc})",
            )
        )

    # Manual clip performance logger (PARTIAL — soft-fail via bolt log-perf; not bolt stats)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Log_Perf import status as _lp_status

        _lp = _lp_status()
        lp_ready = bool(_lp.get("ready"))
        lp_detail = (
            f"Log perf ok; bolt log-perf status (Data/performance_outcomes.jsonl)"
            if lp_ready
            else (
                (_lp.get("hint") or _lp.get("error") or "Log perf unavailable: not ready")
                + " (optional; bolt log-perf status)"
            )
        )
        if len(lp_detail) > 160:
            lp_detail = lp_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "log_perf",
                "live" if lp_ready else "disabled",
                lp_detail,
            )
        )
    except Exception as _lp_exc:
        checks.append(
            _check(
                "integrations",
                "log_perf",
                "disabled",
                f"Log perf unavailable: doctor import failed ({_lp_exc})",
            )
        )

    # SHA256 hash dedupe (PARTIAL — soft-fail via bolt clip-dedupe; not pipeline pHash)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Hash_Dedupe import status as _hd_status

        _hd = _hd_status()
        hd_ready = bool(_hd.get("ready"))
        hd_detail = (
            f"Hash dedupe ok; bolt clip-dedupe status (Data/media_hash_db.json)"
            if hd_ready
            else (
                (_hd.get("hint") or _hd.get("error") or "Hash dedupe unavailable: not ready")
                + " (optional; bolt clip-dedupe status)"
            )
        )
        if len(hd_detail) > 160:
            hd_detail = hd_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "hash_dedupe",
                "live" if hd_ready else "disabled",
                hd_detail,
            )
        )
    except Exception as _hd_exc:
        checks.append(
            _check(
                "integrations",
                "hash_dedupe",
                "disabled",
                f"Hash dedupe unavailable: doctor import failed ({_hd_exc})",
            )
        )

    # Gemini persona loader (PARTIAL — soft-fail via bolt personality; not READY gemini/nexus/chat)
    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.Bolt_Personality import status as _bp_status

        _bp = _bp_status()
        bp_ready = bool(_bp.get("ready"))
        bp_detail = (
            f"Personality ok; bolt personality status (Data/context/bolt-personality.md)"
            if bp_ready
            else (
                (_bp.get("hint") or _bp.get("error") or "Personality unavailable: not ready")
                + " (optional; bolt personality status)"
            )
        )
        if len(bp_detail) > 160:
            bp_detail = bp_detail[:157] + "..."
        checks.append(
            _check(
                "integrations",
                "personality",
                "live" if bp_ready else "disabled",
                bp_detail,
            )
        )
    except Exception as _bp_exc:
        checks.append(
            _check(
                "integrations",
                "personality",
                "disabled",
                f"Personality unavailable: doctor import failed ({_bp_exc})",
            )
        )

    try:
        if str(CORE_DIR) not in sys.path:
            sys.path.insert(0, str(CORE_DIR))
        from modules.FFmpeg_Bin import ffmpeg_bin
    except Exception:
        ffmpeg_bin = None
    ffmpeg_path = ""
    ffmpeg_ok = False
    if ffmpeg_bin is not None:
        try:
            ffmpeg_path = ffmpeg_bin()
            ffmpeg_ok = bool(ffmpeg_path)
            # PATH ffmpeg can exist and still fail to launch (broken dylib).
            import subprocess as _sp

            probe = _sp.run(
                [ffmpeg_path, "-version"], capture_output=True, timeout=5
            )
            ffmpeg_ok = probe.returncode == 0
        except Exception:
            ffmpeg_ok = False
    checks.append(
        _check(
            "integrations",
            "ffmpeg",
            "live" if ffmpeg_ok else "broken",
            f"using {ffmpeg_path}" if ffmpeg_ok else "ffmpeg will not launch — clip cuts fail",
            found=ffmpeg_path,
            fix="" if ffmpeg_ok else "install ffmpeg-full or set BOLT_FFMPEG to a working binary",
        )
    )
    return checks


def collect_memory() -> list[Check]:
    checks: list[Check] = []
    index_path = DATA_ROOT / "memory_index.json"
    if index_path.exists():
        payload = _load_json(index_path, {})
        count = payload.get("entry_count") if isinstance(payload, dict) else None
        detail = f"{_rel(index_path)} present"
        if isinstance(count, int):
            detail += f" ({count} entries)"
        checks.append(_check("memory", "memory index", "live", detail, found=_rel(index_path)))
    else:
        checks.append(
            _check(
                "memory",
                "memory index",
                "missing_file",
                "Data/memory_index.json missing",
                expected=_rel(index_path),
                fix="bolt refresh_memory",
            )
        )

    registry = _load_json(DATA_ROOT / "source_registry.json", {})
    sources = registry.get("sources") if isinstance(registry, dict) else None
    if isinstance(sources, list) and sources:
        missing = [s for s in sources if not s.get("exists")]
        stale = []
        for source in sources:
            path = Path(str(source.get("path") or ""))
            try:
                rel = str(path)
            except Exception:
                rel = ""
            if "/memory/" in rel.replace("\\", "/") and "Data/memory" not in rel.replace(
                "\\", "/"
            ):
                stale.append(source.get("id") or rel)
        if stale:
            checks.append(
                _check(
                    "memory",
                    "source registry",
                    "stale_path",
                    "Think_Learn_Decide still lists repo/memory instead of Data/memory: "
                    + ", ".join(str(s) for s in stale[:6]),
                    found=_rel(DATA_ROOT / "source_registry.json"),
                    fix="Think_Learn_Decide.MEMORY_DIR should be Data/memory",
                )
            )
        elif missing:
            checks.append(
                _check(
                    "memory",
                    "source registry",
                    "fallback",
                    f"{len(missing)}/{len(sources)} registered sources missing on disk",
                    found=_rel(DATA_ROOT / "source_registry.json"),
                )
            )
        else:
            checks.append(
                _check(
                    "memory",
                    "source registry",
                    "live",
                    f"{len(sources)} sources, all present",
                    found=_rel(DATA_ROOT / "source_registry.json"),
                )
            )
    else:
        checks.append(
            _check(
                "memory",
                "source registry",
                "info",
                "no source_registry.json yet (written when the decision engine starts)",
            )
        )
    return checks


def collect_mocks() -> list[Check]:
    weekly = REPO_ROOT / "scripts" / "weekly_analysis.py"
    checks = []
    if weekly.exists():
        text = weekly.read_text(encoding="utf-8")
        wired = "Bolt_Alerts" in text and "def send_sms" in text
        if wired:
            checks.append(
                _check(
                    "mocks",
                    "weekly send_sms/send_email",
                    "live",
                    "bolt weekly --send uses Bolt_Alerts (same path as bolt send)",
                    found=_rel(weekly),
                )
            )
        elif "return False" in text and "def send_sms" in text:
            checks.append(
                _check(
                    "mocks",
                    "weekly send_sms/send_email",
                    "mocked",
                    "weekly_analysis send helpers always return False",
                    found=_rel(weekly),
                    fix="wire send_sms/send_email to modules.Bolt_Alerts",
                )
            )
    return checks


def collect_checks(*, ollama: Optional[dict[str, Any]] = None) -> list[Check]:
    _load_env()
    config = _load_json(CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}
    ollama_info = ollama if ollama is not None else _ollama_probe()
    checks: list[Check] = []
    checks.extend(collect_paths())
    checks.extend(collect_titles(config, ollama_info))
    checks.extend(collect_llm(config, ollama_info))
    checks.extend(collect_queue())
    checks.extend(collect_social())
    checks.extend(collect_integrations(config))
    checks.extend(collect_memory())
    checks.extend(collect_mocks())
    return checks


def summarize(checks: Iterable[Check]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return counts


def format_report(checks: list[Check]) -> str:
    counts = summarize(checks)
    parts = [f"{n} {status.replace('_', ' ')}" for status, n in counts.items() if n]
    lines = [
        "Bolt doctor",
        "===========",
        "  " + "  ·  ".join(parts) if parts else "  no checks",
        "",
    ]
    current = None
    width = max((len(c.name) for c in checks), default=8)
    for check in checks:
        if check.subsystem != current:
            current = check.subsystem
            lines.append(current)
        label = _LABELS.get(check.status, check.status)
        lines.append(f"  {label:<7} {check.name:<{width}}  {check.detail}")
        if check.found and check.status in FAIL_STATUSES:
            lines.append(f"          found     {check.found}")
        if check.expected and check.status in FAIL_STATUSES:
            lines.append(f"          expected  {check.expected}")
        if check.fix and check.status not in OK_STATUSES:
            lines.append(f"          fix       {check.fix}")
    fails = [c for c in checks if c.status in FAIL_STATUSES]
    warns = [c for c in checks if c.status in WARN_STATUSES]
    lines.append("")
    if fails:
        lines.append(f"{len(fails)} disconnected or stale. {len(warns)} mocked/fallback.")
    elif warns:
        lines.append(f"No broken paths. {len(warns)} mocked/fallback item(s).")
    else:
        lines.append("Everything checked is live or intentionally off.")
    return "\n".join(lines)


def report_payload(checks: list[Check]) -> dict[str, Any]:
    fails = [c for c in checks if c.status in FAIL_STATUSES]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": not fails,
        "summary": summarize(checks),
        "checks": [c.as_dict() for c in checks],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Bolt connectivity and paths")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)
    checks = collect_checks()
    payload = report_payload(checks)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(checks))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
