#!/usr/bin/env python3
"""
modules/Think_Learn_Decide.py
=============================
Local assistive decision layer for Bolt.

This module intentionally uses no cloud AI provider. It records events,
proposes safe local actions, and allows the basic clip pipeline to finish
in non-interactive runs.

Important behavior:
- High-risk actions are always blocked.
- Low-risk queue_clip actions are auto-approved by default so process mode
  can produce vertical clips and saved queue output without getting stuck.
- Set "require_manual_approval": true in config.json if you want terminal
  confirmation for every low-risk action.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from modules.notifier import notify

try:
    from modules.Memory_Index import refresh_memory_index, retrieve_memory
except ImportError:
    refresh_memory_index = None
    retrieve_memory = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
MEMORY_DIR = PROJECT_ROOT / "memory"

UNIFIED_MEMORY_FILE = DATA_DIR / "unified_memory.jsonl"
SOURCE_REGISTRY_FILE = DATA_DIR / "source_registry.json"
DECISION_MODEL_FILE = DATA_DIR / "decision_model.json"
AUDIT_LOG_FILE = LOGS_DIR / "decision_audit.log"
PENDING_PROPOSALS_FILE = DATA_DIR / "pending_proposals.json"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _append_jsonl(path: Path, entry: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _format_for_tiktok(clip_path: str, style: str) -> str:
    from modules.Clip_Factory import format_for_tiktok

    return format_for_tiktok(clip_path, style=style)


def _add_to_queue(clip_path: str, title: str, hashtags: List[str], score: float) -> Any:
    from modules.Post_Queue import add_to_queue

    return add_to_queue(
        clip_path=clip_path, title=title, hashtags=hashtags, score=score
    )


@dataclass
class ProposedAction:
    action_id: str
    action: str
    confidence: float
    risk: str
    reason: str
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "risk": self.risk,
            "reason": self.reason,
            "payload": self.payload,
        }


class ThinkLearnDecideEngine:
    """Small local decision helper used by bot.py."""

    def log_nexus_insight(self, insight: str, context: dict = None):
        """Persist Nexus insight into decision history."""
        try:
            from pathlib import Path
            import json
            from datetime import datetime

            log_path = Path("Data/data/decision_history.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)

            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "nexus_insight",
                "insight": insight[:1000],
                "context": context or {}
            }

            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

            # Also push into vector DB so future decisions can retrieve it
            try:
                from modules.Local_Vector_DB import LocalVectorDB
                db = LocalVectorDB()
                db.add_documents([{
                    "id": f"nexus_{datetime.now().timestamp()}",
                    "text": insight,
                    "metadata": {"source": "nexus_insight", "lane": "decision"}
                }])
            except Exception:
                pass

        except Exception as e:
            print(f"Failed to log Nexus insight: {e}")

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.model = _safe_load_json(
            DECISION_MODEL_FILE,
            {
                "weights": {"recency": 0.25, "success_rate": 0.45, "feedback": 0.30},
                "feedback_by_action": {},
                "outcomes_by_action": {},
            },
        )
        self.source_registry = self._build_source_registry()
        _safe_write_json(SOURCE_REGISTRY_FILE, self.source_registry)

    def _build_source_registry(self) -> Dict[str, Any]:
        candidates = [
            ("daily_log", LOGS_DIR / "daily_log.txt", "log"),
            ("memory_hot", MEMORY_DIR / "MEMORY.md", "markdown"),
            ("memory_people", MEMORY_DIR / "people", "markdown_dir"),
            ("memory_projects", MEMORY_DIR / "projects", "markdown_dir"),
            ("memory_context", MEMORY_DIR / "context", "markdown_dir"),
            ("memory_content", MEMORY_DIR / "content", "markdown_dir"),
            ("memory_glossary", MEMORY_DIR / "glossary.md", "markdown"),
            ("ready_to_post", DATA_DIR / "ready_to_post.json", "json"),
            ("rankings", DATA_DIR / "rankings.json", "json"),
            ("seen_clips", PROJECT_ROOT / "seen_clips.json", "json"),
        ]
        return {
            "generated_at": _now_iso(),
            "sources": [
                {
                    "id": sid,
                    "path": str(path),
                    "type": typ,
                    "exists": path.exists(),
                    "last_seen": _now_iso(),
                }
                for sid, path, typ in candidates
            ],
        }

    def ingest_all_sources(self) -> int:
        """Record lightweight existence/preview events from known local files."""
        ingested = 0
        for source in self.source_registry.get("sources", []):
            path = Path(source["path"])
            if not path.exists():
                continue
            try:
                if source["type"] == "markdown":
                    preview = path.read_text(encoding="utf-8")[:300]
                    self.record_event(
                        source["id"],
                        "memory_context",
                        "ingest_markdown",
                        "loaded",
                        0.8,
                        f"Loaded {path.name}",
                        None,
                        {"preview": preview},
                    )
                    ingested += 1
                elif source["type"] == "markdown_dir":
                    for md_file in sorted(path.glob("*.md")):
                        preview = md_file.read_text(encoding="utf-8")[:300]
                        self.record_event(
                            source["id"],
                            "memory_context",
                            "ingest_markdown",
                            "loaded",
                            0.8,
                            f"Loaded {md_file.name}",
                            None,
                            {"preview": preview},
                        )
                        ingested += 1
                elif source["type"] == "json":
                    payload = _safe_load_json(path, None)
                    if payload is not None:
                        keys = list(payload.keys()) if isinstance(payload, dict) else []
                        self.record_event(
                            source["id"],
                            "structured_state",
                            "ingest_json",
                            "loaded",
                            0.85,
                            f"Loaded {path.name}",
                            None,
                            {"keys": keys},
                        )
                        ingested += 1
            except Exception:
                continue
        if ingested:
            notify(f"Ingested {ingested} local memory/state item(s)", level="success")
        return ingested

    def record_event(
        self,
        source: str,
        intent: str,
        action: str,
        result: str,
        confidence: float,
        reason: str,
        feedback: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        _append_jsonl(
            UNIFIED_MEMORY_FILE,
            {
                "timestamp": _now_iso(),
                "source": source,
                "intent": intent,
                "action": action,
                "result": result,
                "confidence": round(float(confidence), 3),
                "reason": reason,
                "feedback": feedback,
                "metadata": metadata or {},
            },
        )

    def think(self, current_context: Dict[str, Any]) -> Dict[str, Any]:
        recording = current_context.get("recording", "session")
        game = current_context.get("game", "Gaming")
        memory_query = self._memory_query_for_context(current_context)
        retrieved = self._retrieve_relevant_memory(memory_query)
        memory_summaries = [
            {
                "title": item.get("title", "Memory"),
                "source": item.get("source", ""),
                "kind": item.get("kind", ""),
                "score": item.get("score", 0),
                "signal": item.get("signal", "context"),
                "signal_reason": item.get("signal_reason", ""),
                "matched_terms": item.get("matched_terms", []),
                "summary": item.get("summary", ""),
            }
            for item in retrieved
        ]
        memory_influence = self._memory_influence(memory_summaries)

        return {
            "situation": f"Bolt processing {recording} for {game}",
            "options": [
                "Queue clips above score floor",
                "Skip low-scoring clips",
                "Save vertical clips for manual review",
            ],
            "tradeoffs": [
                "Higher thresholds improve quality but reduce volume.",
                "Local queueing is safe because it does not publish automatically.",
            ],
            "recommended_next_step": "Format approved clips to vertical and save them to the post queue.",
            "memory_signals_used": len(self._load_recent_memory(50)),
            "memory_query": memory_query,
            "retrieved_memory_count": len(memory_summaries),
            "retrieved_memory": memory_summaries,
            "memory_influence": memory_influence,
        }

    def _memory_query_for_context(self, current_context: Dict[str, Any]) -> str:
        parts = [
            str(current_context.get("game", "")),
            str(current_context.get("recording", "")),
            str(current_context.get("clip_path", "")),
            str(current_context.get("title", "")),
            str(current_context.get("intent", "")),
            "clips decisions queue score creator voice",
        ]
        return " ".join(part for part in parts if part).strip()

    def _retrieve_relevant_memory(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        if retrieve_memory is None or not query:
            return []
        try:
            self._refresh_memory_index_if_enabled()
            return retrieve_memory(query, limit=limit)
        except Exception as exc:
            self.record_event(
                "memory_retrieval",
                "decision_context",
                "retrieve_memory",
                "failed",
                0.2,
                f"Memory retrieval failed: {exc}",
                None,
                {"query": query},
            )
            return []

    def _memory_influence(self, memory_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {"supportive": 0, "cautionary": 0, "mixed": 0, "context": 0}
        strongest: Dict[str, Any] = {}
        strongest_score = -1.0

        for item in memory_items:
            signal = str(item.get("signal") or "context")
            if signal not in counts:
                signal = "context"
            counts[signal] += 1
            score = float(item.get("score") or 0.0)
            if score > strongest_score:
                strongest_score = score
                strongest = {
                    "title": item.get("title", "Memory"),
                    "source": item.get("source", ""),
                    "kind": item.get("kind", ""),
                    "score": item.get("score", 0),
                    "signal": signal,
                    "matched_terms": item.get("matched_terms", []),
                }

        net_direction = "neutral"
        confidence_delta = 0.0
        if counts["supportive"] > counts["cautionary"]:
            net_direction = "supportive"
            confidence_delta = min(0.08, 0.02 * counts["supportive"])
        elif counts["cautionary"] > counts["supportive"]:
            net_direction = "cautionary"
            confidence_delta = max(-0.10, -0.03 * counts["cautionary"])

        return {
            "supportive": counts["supportive"],
            "cautionary": counts["cautionary"],
            "mixed": counts["mixed"],
            "context": counts["context"],
            "net_direction": net_direction,
            "confidence_delta": round(confidence_delta, 3),
            "strongest_match": strongest,
        }

    def _refresh_memory_index_if_enabled(self) -> None:
        if refresh_memory_index is None:
            return
        if self.config.get("memory_auto_refresh", True) is False:
            return
        try:
            refresh_memory_index()
        except Exception as exc:
            self.record_event(
                "memory_retrieval",
                "decision_context",
                "refresh_memory_index",
                "failed",
                0.2,
                f"Memory index refresh failed: {exc}",
                None,
                {},
            )

    def _load_recent_memory(self, limit: int) -> List[Dict[str, Any]]:
        if not UNIFIED_MEMORY_FILE.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in UNIFIED_MEMORY_FILE.read_text(encoding="utf-8").splitlines()[
            -limit:
        ]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    def _get_nexus_insight(self, context: str, task_type: str = "decision") -> str:
        """Get strategic insight from Nexus (Ollama heavy + Grok when needed)."""
        try:
            from modules.Nexus_Creator import NexusCreator
            nexus = NexusCreator()
            result = nexus.consult(
                topic="Analyze this situation and recommend the best next actions",
                context=context,
                task_type=task_type,
                complexity="high" if "high" in task_type or "strategy" in task_type else "medium"
            )
            return result.get("advice", "")
        except Exception as e:
            print(f"Nexus insight skipped: {e}")
            return ""

    def think_and_propose(self, input_data: dict, candidates: list) -> tuple:
        """
        Enhanced version with Nexus + Vector memory enrichment.
        Returns (thought, ranked_proposals)

        What this does:
            1. Run the Nexus enrichment (best-effort, non-blocking).
            2. Run `think()` to retrieve memory context + compute
               `memory_influence` (counts by signal + net_direction +
               confidence_delta + strongest_match).
            3. For each candidate:
                - if the caller already supplied a `memory_influence` dict,
                  keep it untouched (back-compat).
                - otherwise attach the freshly-computed `thought["memory_influence"]`
                  to the candidate so `propose_actions()` can use it.
            4. Delegate ranking + confidence adjustment to `propose_actions`.
        """
        from datetime import datetime

        # Build rich context
        context_parts = [
            f"Input: {input_data}",
            f"Candidates: {candidates}",
            f"Game/Focus: {self.config.get('game', 'Unknown') if hasattr(self, 'config') else 'Unknown'}"
        ]
        full_context = "\n".join(str(p) for p in context_parts)

        # Get Nexus strategic insight (best effort — non-blocking on failure)
        nexus_insight = self._get_nexus_insight(full_context, task_type="decision")

        # Existing thinking path: this populates memory_influence.
        thought = self.think(input_data)
        thought["nexus_insight"] = nexus_insight
        thought["timestamp"] = datetime.now().isoformat()

        # Log the insight (best effort)
        if nexus_insight:
            self.log_nexus_insight(nexus_insight, context={"input": input_data})

        # Attach memory influence when the caller hasn't already done so.
        # We never overwrite a caller-provided `memory_influence` so the
        # caller always wins (test_caller_provided_memory_influence covers this).
        influence = thought.get("memory_influence") if isinstance(thought.get("memory_influence"), dict) else {}
        enriched_candidates = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                enriched_candidates.append(candidate)
                continue
            if isinstance(candidate.get("memory_influence"), dict):
                enriched_candidates.append(candidate)
                continue
            if influence and influence.get("net_direction") not in (None, "", "neutral"):
                enriched_candidates.append({**candidate, "memory_influence": dict(influence)})
            else:
                enriched_candidates.append(candidate)

        # Delegate to propose_actions so memory deltas become confidence
        # deltas and reasons carry the strongest-match title.
        ranked = self.propose_actions(enriched_candidates)
        return thought, ranked

    def _memory_adjustment(self, candidate: Dict[str, Any]) -> tuple[float, str]:
        memory_items = (
            candidate.get("memory_context") or candidate.get("retrieved_memory") or []
        )
        influence = (
            candidate.get("memory_influence")
            if isinstance(candidate.get("memory_influence"), dict)
            else {}
        )
        if influence:
            adjustment = float(influence.get("confidence_delta") or 0.0)
            strongest = (
                influence.get("strongest_match")
                if isinstance(influence.get("strongest_match"), dict)
                else {}
            )
            direction = str(influence.get("net_direction") or "neutral")
            total = sum(
                int(influence.get(key) or 0)
                for key in ("supportive", "cautionary", "mixed", "context")
            )
            title = strongest.get("title", "")
            if abs(adjustment) < 0.005:
                return 0.0, f"memory influence neutral from {total} match(es)"
            verb = "boosted" if adjustment > 0 else "reduced"
            title_part = f"; strongest match: {title}" if title else ""
            return (
                adjustment,
                f"memory {verb} confidence by {abs(adjustment):.2f} ({direction}, {total} match(es)){title_part}",
            )

        if not isinstance(memory_items, list) or not memory_items:
            return 0.0, ""

        adjustment = 0.0
        strongest_title = ""
        strongest_score = 0.0
        for item in memory_items[:5]:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or item.get("text") or "").lower()
            title = str(item.get("title") or "memory")
            match_score = float(item.get("score") or 0.0)
            signal = str(item.get("signal") or "")
            if match_score > strongest_score:
                strongest_score = match_score
                strongest_title = title
            if signal == "supportive" or any(
                term in summary
                for term in (
                    "queue",
                    "queued",
                    "approved",
                    "success",
                    "successful",
                    "ready",
                    "manual review",
                    "format approved",
                    "peak hour",
                )
            ):
                adjustment += min(0.04, match_score * 0.04)
            if signal == "cautionary" or any(
                term in summary
                for term in (
                    "reject",
                    "rejected",
                    "blocked",
                    "failed",
                    "discard",
                    "below",
                    "none approved",
                    "skip",
                    "skipped",
                )
            ):
                adjustment -= min(0.05, match_score * 0.05)

        adjustment = max(-0.10, min(0.08, adjustment))
        if abs(adjustment) < 0.005:
            return (
                0.0,
                f"memory checked, no confidence change from {len(memory_items)} match(es)",
            )

        direction = "boosted" if adjustment > 0 else "reduced"
        title_part = f"; strongest match: {strongest_title}" if strongest_title else ""
        return (
            adjustment,
            f"memory {direction} confidence by {abs(adjustment):.2f} from {len(memory_items)} match(es){title_part}",
        )

    # ── risk classification + scoring helpers ─────────────────────────────────

    _HIGH_RISK_ACTIONS = {"delete_clip", "publish_now"}

    @classmethod
    def _risk_for(cls, action: str) -> str:
        return "high" if str(action) in cls._HIGH_RISK_ACTIONS else "low"

    @staticmethod
    def _base_confidence_from_score(score) -> float:
        """Convert a numeric clip score (0-100 scale typically) into 0..1 confidence.

        Keeps provenance of the original score available on the proposal's
        `payload` so test fixtures that pass `score=70` get a confidence
        around 0.7. Anything that's not a number falls back to 0.5 so the
        pipeline still produces a usable rank.
        """
        try:
            value = float(score)
        except (TypeError, ValueError):
            return 0.5
        # Tame out-of-range inputs instead of raising so a noisy candidate
        # can't crash the ranker.
        if value < 0:
            return 0.0
        if value > 100:
            return 1.0
        return value / 100.0

    @staticmethod
    def _build_reason(candidate: Dict[str, Any], adjustment: float, base_reason: str) -> str:
        """Compose the human-facing reason for a proposed action.

        The test suite asserts two exact substrings:
            - "memory boosted confidence" (any positive adjustment)
            - "memory reduced confidence" (any negative adjustment)
        Plus the strongest-match title when present.
        """
        if abs(adjustment) < 0.005:
            return base_reason
        direction = "boosted" if adjustment > 0 else "reduced"
        strength = abs(adjustment)
        verb = "memory boosted confidence" if direction == "boosted" else "memory reduced confidence"
        influence = candidate.get("memory_influence") if isinstance(candidate.get("memory_influence"), dict) else {}
        strongest = influence.get("strongest_match") if isinstance(influence.get("strongest_match"), dict) else {}
        title = strongest.get("title") if strongest else ""
        title_part = f" — strongest match: {title}" if title else ""
        return f"{base_reason}; {verb} by {strength:.2f}{title_part}"

    @staticmethod
    def _candidate_payload(candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Extract everything except the reserved scoring fields into payload.

        Keeps the engine from accidentally re-scoring a field it doesn't
        know about, while still allowing callers to attach metadata that
        later survives the queue trip.
        """
        payload_keys = {"action", "score", "memory_context", "memory_influence", "retrieved_memory"}
        return {k: v for k, v in candidate.items() if k not in payload_keys}

    def propose_actions(self, candidates: List[Dict[str, Any]]) -> List[ProposedAction]:
        """Rank a list of candidate actions into ProposedAction objects.

        Each candidate is at minimum:
            {"action": str, "score": number, "clip_path": str (optional), ...}

        Optional fields:
            "memory_context":       list[dict]  — memory hits to consider
            "memory_influence":     dict       — pre-computed influence override
            "memory_influence.strongest_match.title": drives the reason wording

        Memory adjustments come from either:
            1. `candidate["memory_influence"]` if present (caller-provided wins)
            2. else `candidate["memory_context"]` / `candidate["retrieved_memory"]`

        Returns proposals sorted by confidence (descending) and assigns each
        a deterministic action_id of the form `<action>:<clip_path>:<rank>`.
        """
        proposals: List[ProposedAction] = []

        for idx, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue

            action = str(candidate.get("action") or "queue_clip")
            score = candidate.get("score", 50)
            confidence = self._base_confidence_from_score(score)
            base_reason = f"score {score} → confidence {confidence:.2f}"

            adjustment, adj_reason = self._memory_adjustment(candidate)
            if adjustment:
                confidence = max(0.0, min(1.0, confidence + adjustment))
                reason = self._build_reason(candidate, adjustment, base_reason)
            else:
                # If memory gave no numeric delta but has a strongest_match
                # title (e.g. caller provided a neutral memory_influence),
                # still surface the title in the reason for traceability.
                reason = base_reason
                influence = candidate.get("memory_influence") if isinstance(candidate.get("memory_influence"), dict) else {}
                strongest = influence.get("strongest_match") if isinstance(influence.get("strongest_match"), dict) else {}
                title = strongest.get("title") if strongest else ""
                net_dir = str(influence.get("net_direction") or "neutral")
                if title and net_dir != "neutral":
                    reason = f"{base_reason}; memory {net_dir} — strongest match: {title}"

            clip_path = str(candidate.get("clip_path") or f"clip_{idx}")
            payload = self._candidate_payload(candidate)
            # Keep the original score inside the payload so downstream stages
            # can recover it (and so existing test_apply_approved_executes_queue_clip
            # still works once we fall back to clip_path for missing values).
            payload.setdefault("score", float(score) if isinstance(score, (int, float)) else 0.0)
            payload.setdefault("clip_path", clip_path)

            proposals.append(
                ProposedAction(
                    action_id=f"{action}:{Path(clip_path).name}:{idx}",
                    action=action,
                    confidence=confidence,
                    risk=self._risk_for(action),
                    reason=reason,
                    payload=payload,
                )
            )

        # Stable sort by confidence desc; ties broken by original order so
        # scores with equal confidence come out in user-supplied order.
        proposals.sort(key=lambda p: p.confidence, reverse=True)
        return proposals

    def confirm_action(self, proposal: ProposedAction) -> bool:
        """
        Confirm a proposed action.

        Low-risk queue_clip actions are auto-approved by default so:
            python bot.py process
        actually finishes the cycle and saves output.
        """
        if proposal.risk == "high":
            return False

        require_manual = bool(self.config.get("require_manual_approval", False))
        if not require_manual:
            return True

        if not sys_stdin_interactive():
            return False

        prompt = (
            f"Approve action '{proposal.action}' for "
            f"{proposal.payload.get('clip_path', 'clip')} "
            f"[confidence={proposal.confidence:.2f}]? [y/N]: "
        )
        answer = input(prompt).strip().lower()
        return answer in {"y", "yes"}

    def enqueue_pending_proposal(self, proposal: ProposedAction) -> None:
        pending = _safe_load_json(PENDING_PROPOSALS_FILE, [])
        pending.append(
            {
                "queued_at": _now_iso(),
                "status": "pending",
                "proposal": proposal.as_dict(),
            }
        )
        _safe_write_json(PENDING_PROPOSALS_FILE, pending)

    def pending_proposals(self) -> List[Dict[str, Any]]:
        return _safe_load_json(PENDING_PROPOSALS_FILE, [])

    def resolve_pending(self, action_id: str, approved: bool, note: str = "") -> bool:
        pending = _safe_load_json(PENDING_PROPOSALS_FILE, [])
        changed = False
        for item in pending:
            proposal = item.get("proposal", {})
            if (
                proposal.get("action_id") == action_id
                and item.get("status") == "pending"
            ):
                item["status"] = "approved" if approved else "rejected"
                item["resolved_at"] = _now_iso()
                item["note"] = note
                self.learn_from_feedback(
                    proposal.get("action", "queue_clip"), approved, note
                )
                changed = True
                break
        if changed:
            _safe_write_json(PENDING_PROPOSALS_FILE, pending)
        return changed

    def apply_approved(self) -> int:
        pending = _safe_load_json(PENDING_PROPOSALS_FILE, [])
        applied_count = 0
        for item in pending:
            if item.get("status") != "approved" or item.get("applied_at"):
                continue
            ok = self._execute_proposal(item.get("proposal", {}))
            item["applied_at"] = _now_iso()
            item["apply_result"] = "success" if ok else "failed"
            applied_count += 1 if ok else 0
        _safe_write_json(PENDING_PROPOSALS_FILE, pending)
        return applied_count

    def _execute_proposal(self, proposal: Dict[str, Any]) -> bool:
        payload = proposal.get("payload", {})
        clip_path = payload.get("clip_path")
        if proposal.get("action") != "queue_clip" or not clip_path:
            return False
        try:
            style = payload.get("style", "letterbox")
            vertical = _format_for_tiktok(clip_path, style=style)
            title = payload.get("title") or Path(clip_path).stem.replace("_", " ")
            hashtags = payload.get("hashtags") or []
            score = float(payload.get("score", 50))
            _add_to_queue(
                clip_path=vertical, title=title, hashtags=hashtags, score=score
            )
            return True
        except Exception:
            return False

    def learn_from_feedback(
        self, action: str, accepted: bool, feedback_text: str = ""
    ) -> None:
        feedback_map = self.model.setdefault("feedback_by_action", {})
        feedback_map[action] = float(feedback_map.get(action, 0.0)) + (
            1.0 if accepted else -1.0
        )
        _safe_write_json(DECISION_MODEL_FILE, self.model)
        self.record_event(
            "decision_feedback",
            "user_preference",
            action,
            "accepted" if accepted else "rejected",
            0.9,
            "Feedback recorded",
            feedback_text,
            {},
        )

    def learn_from_outcome(
        self, action: str, success: bool, details: Dict[str, Any]
    ) -> None:
        outcomes = self.model.setdefault("outcomes_by_action", {})
        stats = outcomes.setdefault(action, {"ok": 0, "total": 0})
        stats["total"] = int(stats.get("total", 0)) + 1
        if success:
            stats["ok"] = int(stats.get("ok", 0)) + 1
        _safe_write_json(DECISION_MODEL_FILE, self.model)
        self.record_event(
            "decision_outcome",
            "execution_result",
            action,
            "success" if success else "failed",
            0.95,
            "Outcome captured",
            None,
            details,
        )

    def enforce_action_policy(self, proposal: ProposedAction) -> bool:
        allowlist = set(self.config.get("decision_allowlist", ["queue_clip"]))
        denylist = set(
            self.config.get("decision_denylist", ["delete_clip", "publish_now"])
        )
        if proposal.action in denylist:
            return False
        return proposal.action in allowlist

    def audit(self, phase: str, payload: Dict[str, Any]) -> None:
        _append_jsonl(
            AUDIT_LOG_FILE,
            {"timestamp": _now_iso(), "phase": phase, "payload": payload},
        )


class BrainController(ThinkLearnDecideEngine):
    """
    Backward-compatible name for Bolt's merged brain.

    Old files may still call BrainController(config, creator_brain).
    The new engine is ThinkLearnDecideEngine(config), so this wrapper keeps
    older calls working while the project transitions.
    """

    def __init__(self, config: Dict[str, Any], creator_brain: str = ""):
        super().__init__(config)
        self.creator_brain = creator_brain or ""


def sys_stdin_interactive() -> bool:
    try:
        return os.isatty(0)
    except Exception:
        return False


def review_pending_cli() -> int:
    engine = ThinkLearnDecideEngine({"require_manual_approval": True})
    pending = [p for p in engine.pending_proposals() if p.get("status") == "pending"]
    if not pending:
        print("No pending proposals.")
        return 0
    print(f"Pending proposals: {len(pending)}")
    for idx, item in enumerate(pending, start=1):
        proposal = item.get("proposal", {})
        print(
            f"{idx}. {proposal.get('action_id')} | {proposal.get('action')} | clip={proposal.get('payload', {}).get('clip_path', '-')}"
        )
    if not sys_stdin_interactive():
        print("Non-interactive mode: run this command in a terminal to approve/reject.")
        return 1
    approve_all = input("Approve all pending proposals? [y/N]: ").strip().lower() in {
        "y",
        "yes",
    }
    for item in pending:
        proposal = item.get("proposal", {})
        action_id = proposal.get("action_id", "")
        if not action_id:
            continue
        if approve_all:
            engine.resolve_pending(action_id, approved=True, note="approved_all_batch")
        else:
            answer = input(f"Approve {action_id}? [y/N]: ").strip().lower()
            engine.resolve_pending(
                action_id, approved=answer in {"y", "yes"}, note="manual_batch_review"
            )
    print("Pending review complete.")
    return 0


def apply_approved_cli() -> int:
    engine = ThinkLearnDecideEngine({})
    applied = engine.apply_approved()
    print(f"Applied approved proposals: {applied}")
    return 0


if __name__ == "__main__":
    import sys

    if "--review-pending" in sys.argv:
        raise SystemExit(review_pending_cli())
    if "--apply-approved" in sys.argv:
        raise SystemExit(apply_approved_cli())
    print(
        "Usage: python -m modules.Think_Learn_Decide --review-pending|--apply-approved"
    )
