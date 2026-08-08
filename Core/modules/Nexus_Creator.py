#!/usr/bin/env python3
"""
Nexus Creator — Strategic AI Content + Product Testing Consultant

Preference (Google used sparingly):
  1. Ollama (local, free) for everyday / when paid is off
  2. Grok (xAI API) when paid is allowed — preferred cloud quality
  3. Gemini only if ``NEXUS_USE_GEMINI=true`` (off by default)

Paid Grok is opt-in via:
  - env ``NEXUS_ALLOW_PAID=true``, or
  - ``consult(..., allow_paid=True)``, or
  - CLI ``bolt nexus "…" --paid``

Note: SuperGrok *subscription* (app/web) ≠ free ``XAI_API_KEY`` usage.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    OpenAI = None  # type: ignore


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


class NexusCreator:
    def __init__(self):
        self.xai_api_key = os.getenv("XAI_API_KEY")
        self.grok_model = os.getenv("GROK_MODEL") or os.getenv(
            "BOLT_XAI_MODEL", "grok-4.5"
        )
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        # Gemini is opt-in only — prefer Ollama / Grok over Google.
        self.use_gemini = _env_bool("NEXUS_USE_GEMINI", default=False)
        self.preferred_provider = os.getenv("NEXUS_PREFERRED", "ollama").lower().strip()
        # Free by default — SuperGrok chat sub ≠ free xAI API.
        self.allow_paid_default = _env_bool("NEXUS_ALLOW_PAID", default=False)

    def _get_client(self, provider: str):
        if OpenAI is None:
            raise ValueError("openai package not installed")
        # Bound request time so a stuck provider can't freeze the pipeline
        # for hours during bolt recordings / setup.
        timeout = float(os.getenv("NEXUS_TIMEOUT_SEC", "45"))
        if provider == "ollama":
            return OpenAI(
                base_url=self.ollama_base_url, api_key="ollama", timeout=timeout
            )
        if provider == "grok" and self.xai_api_key:
            return OpenAI(
                api_key=self.xai_api_key,
                base_url="https://api.x.ai/v1",
                timeout=timeout,
            )
        raise ValueError(f"Provider {provider} not configured")

    def _paid_allowed(self, allow_paid: Optional[bool] = None) -> bool:
        if allow_paid is not None:
            return bool(allow_paid)
        return self.allow_paid_default

    def _should_use_grok(
        self,
        task_type: str,
        complexity: str = "medium",
        allow_paid: Optional[bool] = None,
    ) -> bool:
        """Grok only when paid path is explicitly allowed AND task is high-value."""
        if not self._paid_allowed(allow_paid) or not self.xai_api_key:
            return False
        high_value = {
            "strategy",
            "product_testing",
            "sponsor",
            "decision",
            "deep_analysis",
            "career",
            "review",
            "m_tier",
        }
        return complexity == "high" or task_type in high_value

    def _is_ollama_healthy(self) -> bool:
        try:
            import requests

            resp = requests.get(
                self.ollama_base_url.replace("/v1", "/api/tags"), timeout=3
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _enrich_with_vector_memory(
        self, topic: str, context: str = None, task_type: str = None
    ):
        # Skip entirely when Ollama (embeddings backend) is down — LocalVectorDB
        # fails fast, but avoid even constructing it on the hot path.
        if not self._is_ollama_healthy():
            print("Vector DB enrichment skipped: Ollama not reachable")
            return context or ""
        try:
            from modules.Local_Vector_DB import LocalVectorDB

            vector_db = LocalVectorDB()
            # Don't filter by lane on first pass — many docs are tagged
            # "general" and a strict lane filter returns empty results.
            relevant = vector_db.search(
                query=topic + (f" {context}" if context else ""),
                n_results=8,
                filter=None,
            )
            if not relevant:
                return context or ""
            enriched = "\n\n--- Relevant Memory ---\n" + "\n\n".join(
                [
                    f"Source: {r['metadata'].get('file', 'unknown')}\n{r['text'][:700]}"
                    for r in relevant
                ]
            )
            return (context or "") + enriched
        except Exception as e:
            print(f"Vector DB enrichment skipped: {e}")
            return context or ""

    def _build_system_prompt(self) -> str:
        brain_path = Path("Core/bolt_brain.md")
        brain = (
            brain_path.read_text(encoding="utf-8")[:3000]
            if brain_path.exists()
            else ""
        )
        return f"""You are Nexus, Billy's strategic AI teammate.
Creator profile: {brain}
Focus: content creation, product testing, gaming, skincare, AI development, sponsorships."""

    def _build_user_prompt(self, topic: str, full_context: str) -> str:
        return (
            f"Topic: {topic}\nContext + Memory:\n{full_context}\n\n"
            "Give detailed, actionable advice with next steps."
        )

    def _pick_provider(
        self,
        task_type: str,
        complexity: str,
        allow_paid: Optional[bool],
        force_provider: Optional[str],
    ) -> str:
        if force_provider:
            return force_provider.lower().strip()

        # High-value work → Grok when paid path is allowed (preferred over Gemini).
        if self._should_use_grok(task_type, complexity, allow_paid):
            return "grok"

        preferred = self.preferred_provider
        if preferred == "ollama" and self._is_ollama_healthy():
            return "ollama"
        if (
            preferred == "gemini"
            and self.use_gemini
            and self.gemini_key
        ):
            return "gemini"
        if preferred == "grok" and self._paid_allowed(allow_paid) and self.xai_api_key:
            return "grok"

        # Everyday free path: local Ollama
        if self._is_ollama_healthy():
            return "ollama"

        # Paid cloud when allowed (Grok preferred)
        if self._paid_allowed(allow_paid) and self.xai_api_key:
            return "grok"

        # Gemini only if explicitly enabled — last cloud option
        if self.use_gemini and self.gemini_key:
            return "gemini"

        return "none"

    def _ask_gemini(self, system: str, user: str) -> str:
        from modules.Gemini_Client import ask_gemini

        return ask_gemini(
            user,
            system=system,
            model=self.gemini_model,
            temperature=0.7,
            max_output_tokens=2800,
            json_mode=False,
            timeout=float(os.getenv("NEXUS_TIMEOUT_SEC", "45")),
        )

    def consult(
        self,
        topic: str,
        context: str = None,
        task_type: str = "general",
        complexity: str = "medium",
        allow_paid: Optional[bool] = None,
        force_provider: Optional[str] = None,
    ):
        full_context = self._enrich_with_vector_memory(topic, context, task_type)
        provider = self._pick_provider(
            task_type, complexity, allow_paid, force_provider
        )

        if provider == "none":
            print(
                "Nexus: no provider available "
                "(start Ollama, set NEXUS_ALLOW_PAID=true for Grok, "
                "or NEXUS_USE_GEMINI=true for Google as last resort)"
            )
            return {
                "advice": "",
                "provider": "none",
                "model": "",
                "task_type": task_type,
            }

        system = self._build_system_prompt()
        user = self._build_user_prompt(topic, full_context)

        try:
            if provider == "gemini":
                print("Nexus: using Gemini (free tier)")
                advice = self._ask_gemini(system, user)
                if advice.startswith("LLM unavailable"):
                    print(f"gemini failed: {advice}")
                    return {
                        "advice": "",
                        "provider": "fallback",
                        "model": "",
                        "task_type": task_type,
                    }
                model = self.gemini_model
            else:
                if provider == "grok":
                    print("Nexus: using Grok (xAI API — paid usage)")
                elif provider == "ollama":
                    print("Nexus: using Ollama (local, free)")
                client = self._get_client(provider)
                model = self.grok_model if provider == "grok" else self.ollama_model
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.7,
                    max_tokens=1600 if provider == "grok" else 2800,
                )
                advice = (response.choices[0].message.content or "").strip()

            advice = (advice or "").strip()
            if advice:
                self._log_advice(topic, advice, provider, model, task_type)

            return {
                "advice": advice,
                "provider": provider,
                "model": model,
                "task_type": task_type,
            }
        except Exception as e:
            print(f"{provider} failed: {e}")
            return {
                "advice": "",
                "provider": "fallback",
                "model": "",
                "task_type": task_type,
            }

    def _log_advice(
        self, topic: str, advice: str, provider: str, model: str, task_type: str
    ):
        log_path = Path("Data/data/nexus_advice.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "provider": provider,
            "model": model,
            "task_type": task_type,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # Convenience methods
    def optimize_caption(
        self, clip_name: str, description: str, platform: str = "tiktok"
    ):
        return self.consult(
            f"Optimize caption for {clip_name}", description, "caption"
        )

    def suggest_next_content(self, performance_data=None):
        # Strategy is high-value; still free unless NEXUS_ALLOW_PAID=true
        return self.consult(
            "Suggest next content", str(performance_data), "strategy", "high"
        )


if __name__ == "__main__":
    import sys

    nexus = NexusCreator()
    topic = sys.argv[1] if len(sys.argv) > 1 else "Test query"
    result = nexus.consult(topic)
    print(result["advice"])
