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

    health_check = REPO_ROOT / "scripts" / "health_check.py"
    if health_check.exists():
        checks.append(
            _check(
                "paths",
                "legacy health_check.py",
                "info",
                "pre-reorg CWD paths; not wired to the CLI. Use bolt doctor.",
                found=_rel(health_check),
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
            "info",
            "no trainer or A/B loop exists. Preview/edit: bolt queue title. "
            "Performance: bolt stats / bolt log_perf. Unit tests cover Title_Generator.",
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
                tiktok.get("next_step") or "TikTok API paused; log_perf after posting",
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
            "DISCORD_WEBHOOK_URL set" if discord else "unset (Bolt alerts use Mac/iMessage/email)",
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
