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

    def think_and_propose(
        self,
        current_context: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], List[ProposedAction]]:
        """Single-call bridge: think about the situation, then rank actions.

        Calls ``self.think(current_context)`` to retrieve relevant memory
        and compute ``memory_influence``. That influence is then attached
        to each candidate that doesn't already carry one, so the existing
        ``propose_actions`` ranking gets memory-aware confidence boosts /
        reductions automatically.

        Callers that want to control the memory flow manually can still
        call ``think`` and ``propose_actions`` separately — this method
        is a convenience, not a replacement.

        Returns a ``(thought, proposals)`` tuple. ``thought`` is the dict
        returned by ``think``; ``proposals`` is the ranked list from
        ``propose_actions``.
        """
        thought = self.think(current_context)
        influence = thought.get("memory_influence") or {}

        # If retrieval returned nothing meaningful, do not touch the
        # candidates — let propose_actions fall through to its existing
        # plain-score path.
        if not influence or not isinstance(influence, dict):
            return thought, self.propose_actions(candidates)

        net_direction = str(influence.get("net_direction") or "neutral")
        total = sum(
            int(influence.get(key) or 0)
            for key in ("supportive", "cautionary", "mixed", "context")
        )
        if net_direction == "neutral" or total == 0:
            return thought, self.propose_actions(candidates)

        enriched: List[Dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                enriched.append(candidate)
                continue
            # Don't overwrite an influence the caller already attached.
            if isinstance(candidate.get("memory_influence"), dict):
                enriched.append(candidate)
                continue
            enriched.append(
                {**candidate, "memory_influence": dict(influence)}
            )
        return thought, self.propose_actions(enriched)

    def propose_actions(self, candidates: List[Dict[str, Any]]) -> List[ProposedAction]:
        proposed: List[ProposedAction] = []
        for idx, candidate in enumerate(candidates, start=1):
            action = candidate.get("action", "queue_clip")
            score = float(candidate.get("score", 0))
            memory_adjustment, memory_reason = self._memory_adjustment(candidate)
            confidence = max(
                0.0, min(0.99, (score / 100.0) * 0.6 + 0.35 + memory_adjustment)
            )
            risk = "high" if action in {"delete_clip", "publish_now"} else "low"
            reason = f"Local action proposal from clip score={score:.1f}"
            if memory_reason:
                reason += f"; {memory_reason}"
            proposed.append(
                ProposedAction(
                    action_id=f"act_{idx}_{int(score)}",
                    action=action,
                    confidence=confidence,
                    risk=risk,
                    reason=reason,
                    payload=candidate,
                )
            )
        proposed.sort(key=lambda p: p.confidence, reverse=True)
        return proposed

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
