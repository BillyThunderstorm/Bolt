#!/usr/bin/env python3
"""Minimal Gemini REST client (free-tier Google AI Studio keys).

Uses plain HTTPS + `requests` so Bolt does not depend on the optional
`google-genai` package being installed in the active venv.

Soft-fail convention matches LLM_Handler: failures return
``LLM unavailable: …`` strings (never raise for missing key / HTTP errors).

CLI (via ``bolt gemini`` or ``python -m modules.Gemini_Client``)::

    bolt gemini status
    bolt gemini status --probe
    bolt gemini ask "one sentence tip for TikTok titles"

Nexus still only calls Gemini when ``NEXUS_USE_GEMINI=true`` (off by default).
READY means this client is usable and honest about key / opt-in readiness.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import requests

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def has_gemini_key() -> bool:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key)


def ask_gemini(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    json_mode: bool = False,
    timeout: float = 45.0,
) -> str:
    """
    Call Gemini generateContent. Returns response text, or a short
    ``LLM unavailable: …`` string on failure (same convention as LLM_Handler).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "LLM unavailable: GEMINI_API_KEY not set"

    use_model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    url = f"{API_BASE}/models/{use_model}:generateContent"

    user_text = prompt
    if system:
        user_text = f"{system.strip()}\n\n{prompt}"

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=body,
            timeout=timeout,
        )
        if resp.status_code != 200:
            # Avoid leaking key material; keep body short for logs.
            detail = (resp.text or "")[:180].replace("\n", " ")
            return f"LLM unavailable: Gemini HTTP {resp.status_code}: {detail}"

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            # Blocked / empty — surface finish reason when present.
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason") or "empty candidates"
            return f"LLM unavailable: Gemini returned no content ({reason})"

        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        text = "".join(texts).strip()
        if not text:
            return "LLM unavailable: Gemini returned empty text"
        return text
    except requests.Timeout:
        return "LLM unavailable: Gemini request timed out"
    except Exception as exc:
        return f"LLM unavailable: {str(exc)[:160]}"


def status(*, probe: bool = False) -> dict[str, Any]:
    """Key / model / Nexus opt-in readiness. Never raises; never spends quota unless probe=True."""
    has_key = has_gemini_key()
    model = (os.getenv("GEMINI_MODEL", "") or "").strip() or "gemini-2.5-flash"
    nexus_use = _env_bool("NEXUS_USE_GEMINI", False)

    info: dict[str, Any] = {
        "ready": has_key,
        "has_key": has_key,
        "model": model,
        "nexus_use_gemini": nexus_use,
        "hint": "",
    }

    if not has_key:
        info["hint"] = (
            "Set GEMINI_API_KEY in .env (Google AI Studio free key). "
            "Nexus last-resort still needs NEXUS_USE_GEMINI=true (off by default)."
        )
    elif not nexus_use:
        info["hint"] = (
            "Client ready for bolt gemini ask / direct calls. "
            "Nexus uses Gemini only when NEXUS_USE_GEMINI=true (still off)."
        )
    else:
        info["hint"] = "Client ready; Nexus Gemini opt-in is on."

    if probe:
        if not has_key:
            info["probe_ok"] = False
            info["probe_detail"] = "LLM unavailable: GEMINI_API_KEY not set"
        else:
            reply = ask_gemini(
                "Reply with OK",
                system="Connectivity probe. Reply with exactly: OK",
                temperature=0.0,
                max_output_tokens=16,
            )
            info["probe_ok"] = not reply.startswith("LLM unavailable:")
            info["probe_detail"] = (reply or "")[:240]

    return info


def _cli_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print("ready:", info["ready"])
    print("has_key:", info["has_key"])
    print("model:", info["model"])
    print("nexus_use_gemini:", info["nexus_use_gemini"])
    if info.get("hint"):
        print("hint:", info["hint"])
    if probe:
        print("probe_ok:", info.get("probe_ok"))
        print("probe_detail:", info.get("probe_detail"))
    return 0


def _cli_ask(prompt: str) -> int:
    reply = ask_gemini(prompt)
    print(reply)
    if reply.startswith("LLM unavailable:"):
        return 1
    return 0


def _cli_help() -> int:
    print("Usage: bolt gemini [status|ask \"…\"]")
    print("  status [--json] [--probe]  Key / model / Nexus opt-in readiness (default)")
    print("  ask \"prompt\"               Call ask_gemini; soft-fails with LLM unavailable:")
    print()
    print("  bolt gemini status")
    print("  bolt gemini status --probe")
    print('  bolt gemini ask "one sentence tip for TikTok titles"')
    print()
    print("Nexus still requires NEXUS_USE_GEMINI=true to use Gemini as last resort.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        return _cli_status()

    cmd = args[0]
    if cmd in ("-h", "--help", "help"):
        return _cli_help()

    if cmd in ("status", "ready") or cmd in ("--json", "--probe"):
        rest = args[1:] if cmd in ("status", "ready") else args
        as_json = "--json" in rest
        probe = "--probe" in rest
        unknown = [a for a in rest if a not in ("--json", "--probe")]
        if unknown:
            print(f"Unknown status flag(s): {' '.join(unknown)}", file=sys.stderr)
            return 2
        return _cli_status(as_json=as_json, probe=probe)

    if cmd == "ask":
        prompt_parts = args[1:]
        if not prompt_parts:
            print('Usage: bolt gemini ask "prompt"', file=sys.stderr)
            return 2
        return _cli_ask(" ".join(prompt_parts))

    print(f"Unknown arg: {cmd}", file=sys.stderr)
    _cli_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
