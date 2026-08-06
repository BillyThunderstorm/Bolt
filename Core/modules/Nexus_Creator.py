#!/usr/bin/env python3
"""
Nexus Creator — Strategic AI Content + Product Testing Consultant
Heavy Ollama + Occasional Grok + Local Vector DB
"""

import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")

class NexusCreator:
    def __init__(self):
        self.xai_api_key = os.getenv("XAI_API_KEY")
        self.grok_model = os.getenv("GROK_MODEL", "grok-4.5")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.preferred_provider = os.getenv("NEXUS_PREFERRED", "ollama")

    def _get_client(self, provider: str):
        # Bound request time so a stuck provider can't freeze the pipeline
        # for hours during bolt recordings / setup.
        timeout = float(os.getenv("NEXUS_TIMEOUT_SEC", "45"))
        if provider == "ollama":
            return OpenAI(
                base_url=self.ollama_base_url, api_key="ollama", timeout=timeout
            )
        elif provider == "grok" and self.xai_api_key:
            return OpenAI(
                api_key=self.xai_api_key,
                base_url="https://api.x.ai/v1",
                timeout=timeout,
            )
        elif provider == "gemini" and self.gemini_key:
            print("Using Gemini fallback")
            return None
        raise ValueError(f"Provider {provider} not configured")

    def _should_use_grok(self, task_type: str, complexity: str = "medium") -> bool:
        high_value = {"strategy", "product_testing", "sponsor", "decision", "deep_analysis", "career", "review", "m_tier"}
        return (complexity == "high" or task_type in high_value) and self.xai_api_key

    def _is_ollama_healthy(self) -> bool:
        try:
            import requests
            resp = requests.get(self.ollama_base_url.replace("/v1", "/api/tags"), timeout=3)
            return resp.status_code == 200
        except:
            return False

    def _enrich_with_vector_memory(self, topic: str, context: str = None, task_type: str = None):
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
                [f"Source: {r['metadata'].get('file', 'unknown')}\n{r['text'][:700]}" for r in relevant]
            )
            return (context or "") + enriched
        except Exception as e:
            print(f"Vector DB enrichment skipped: {e}")
            return context or ""

    def _build_system_prompt(self) -> str:
        brain_path = Path("Core/bolt_brain.md")
        brain = brain_path.read_text(encoding="utf-8")[:3000] if brain_path.exists() else ""
        return f"""You are Nexus, Billy's strategic AI teammate.
Creator profile: {brain}
Focus: content creation, product testing, gaming, skincare, AI development, sponsorships."""

    def _build_user_prompt(self, topic: str, full_context: str) -> str:
        return f"Topic: {topic}\nContext + Memory:\n{full_context}\n\nGive detailed, actionable advice with next steps."

    def consult(self, topic: str, context: str = None, task_type: str = "general", complexity: str = "medium"):
        full_context = self._enrich_with_vector_memory(topic, context, task_type)

        if self._should_use_grok(task_type, complexity):
            provider = "grok"
        elif self.preferred_provider == "ollama" and self._is_ollama_healthy():
            provider = "ollama"
        elif self.gemini_key:
            provider = "gemini"
        elif self.xai_api_key:
            provider = "grok"
        else:
            print("Nexus: no provider available (Ollama down, no XAI/Gemini keys)")
            return {
                "advice": "",
                "provider": "none",
                "model": "",
                "task_type": task_type,
            }

        try:
            client = self._get_client(provider)
            if client is None:
                return {
                    "advice": "",
                    "provider": provider,
                    "model": "",
                    "task_type": task_type,
                }
            model = self.grok_model if provider == "grok" else self.ollama_model

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": self._build_user_prompt(topic, full_context)}
                ],
                temperature=0.7,
                max_tokens=1600 if provider == "grok" else 2800,
            )

            advice = (response.choices[0].message.content or "").strip()
            self._log_advice(topic, advice, provider, model, task_type)

            return {
                "advice": advice,
                "provider": provider,
                "model": model,
                "task_type": task_type
            }
        except Exception as e:
            print(f"{provider} failed: {e}")
            return {"advice": "", "provider": "fallback", "model": "", "task_type": task_type}

    def _log_advice(self, topic: str, advice: str, provider: str, model: str, task_type: str):
        log_path = Path("Data/data/nexus_advice.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "provider": provider,
            "model": model,
            "task_type": task_type
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # Convenience methods
    def optimize_caption(self, clip_name: str, description: str, platform: str = "tiktok"):
        return self.consult(f"Optimize caption for {clip_name}", description, "caption")

    def suggest_next_content(self, performance_data=None):
        return self.consult("Suggest next content", str(performance_data), "strategy", "high")


if __name__ == "__main__":
    import sys
    nexus = NexusCreator()
    topic = sys.argv[1] if len(sys.argv) > 1 else "Test query"
    result = nexus.consult(topic)
    print(result["advice"])