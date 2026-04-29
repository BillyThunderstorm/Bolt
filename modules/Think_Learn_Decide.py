#!/usr/bin/env python3
"""
modules/Think_Learn_Decide.py
=============================
Bolt's assistive intelligence loop:
  - Think: assemble context from current session + historical memory
  - Learn: ingest events/outcomes/feedback into a unified memory store
  - Decide: rank candidate actions and require explicit confirmation
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from modules.notifier import notify


PROJECT_ROOT = Path(__file__).parent.parent
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

    return add_to_queue(clip_path=clip_path, title=title, hashtags=hashtags, score=score)


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
    """
    Assistive decision layer for Bolt.

    Canonical event schema:
      timestamp, source, intent, action, result, confidence, reason, feedback, metadata
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.model = _safe_load_json(
            DECISION_MODEL_FILE,
            {
                "weights": {
                    "recency": 0.25,
                    "success_rate": 0.45,
                    "feedback": 0.30,
                },
                "feedback_by_action": {},
                "outcomes_by_action": {},
            },
        )
        self.source_registry = self._build_source_registry()
        _safe_write_json(SOURCE_REGISTRY_FILE, self.source_registry)

    # ---------------------------- Inventory + ingestion -------------------------
    def _build_source_registry(self) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        candidates = [
            ("daily_log", LOGS_DIR / "daily_log.txt", "log"),
            ("bolt_logs", LOGS_DIR, "jsonl_log_dir"),
            ("memory_hot", MEMORY_DIR / "MEMORY.md", "markdown"),
            ("memory_people", MEMORY_DIR / "people", "markdown_dir"),
            ("memory_projects", MEMORY_DIR / "projects", "markdown_dir"),
            ("memory_context", MEMORY_DIR / "context", "markdown_dir"),
            ("memory_glossary", MEMORY_DIR / "glossary.md", "markdown"),
            ("session_tasks", PROJECT_ROOT / "session_tasks.json", "json"),
            ("brain_state", DATA_DIR / "brain_state.json", "json"),
            ("ready_to_post", DATA_DIR / "ready_to_post.json", "json"),
            ("rankings", DATA_DIR / "rankings.json", "json"),
            ("clip_history", PROJECT_ROOT / "clip_history.json", "json"),
            ("seen_clips", PROJECT_ROOT / "seen_clips.json", "json"),
            ("checklist_progress", LOGS_DIR / "checklist_progress.json", "json"),
            ("viral_title_model", PROJECT_ROOT / "viral_titles_model.json", "json"),
        ]
        for source_id, path, source_type in candidates:
            entries.append(
                {
                    "id": source_id,
                    "path": str(path),
                    "type": source_type,
                    "exists": path.exists(),
                    "last_seen": _now_iso(),
                }
            )
        return {"generated_at": _now_iso(), "sources": entries}

    def ingest_all_sources(self) -> int:
        ingested = 0
        for source in self.source_registry.get("sources", []):
            source_id = source["id"]
            path = Path(source["path"])
            source_type = source["type"]
            if not path.exists():
                continue
            if source_type in ("markdown", "markdown_dir"):
                ingested += self._ingest_markdown_source(source_id, path, source_type)
            elif source_type in ("json", "jsonl_log_dir", "log"):
                ingested += self._ingest_structured_source(source_id, path, source_type)
        if ingested:
            notify(
                f"Ingested {ingested} historical event(s) into unified memory",
                level="success",
                reason=f"Memory store updated at {UNIFIED_MEMORY_FILE}",
            )
        return ingested

    def _ingest_markdown_source(self, source_id: str, path: Path, source_type: str) -> int:
        count = 0
        files: Iterable[Path]
        if source_type == "markdown":
            files = [path]
        else:
            files = sorted(path.glob("*.md"))

        for md_file in files:
            try:
                content = md_file.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not content:
                continue
            self.record_event(
                source=source_id,
                intent="memory_context",
                action="ingest_markdown",
                result="loaded",
                confidence=0.8,
                reason=f"Ingested markdown memory from {md_file.name}",
                feedback=None,
                metadata={"file": str(md_file), "preview": content[:300]},
            )
            count += 1
        return count

    def _ingest_structured_source(self, source_id: str, path: Path, source_type: str) -> int:
        count = 0
        if source_type == "json":
            payload = _safe_load_json(path, None)
            if payload is not None:
                self.record_event(
                    source=source_id,
                    intent="structured_state",
                    action="ingest_json",
                    result="loaded",
                    confidence=0.85,
                    reason=f"Ingested JSON state from {path.name}",
                    feedback=None,
                    metadata={"file": str(path), "keys": list(payload.keys()) if isinstance(payload, dict) else []},
                )
                count += 1
            return count

        if source_type == "jsonl_log_dir":
            for log_path in sorted(path.glob("Bolt_*.log"))[-5:]:
                count += self._ingest_jsonl_log(source_id, log_path)
            return count

        if source_type == "log":
            try:
                lines = path.read_text(encoding="utf-8").splitlines()[-100:]
            except Exception:
                return 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                self.record_event(
                    source=source_id,
                    intent="runtime_history",
                    action="ingest_log_line",
                    result="loaded",
                    confidence=0.6,
                    reason="Parsed line from daily log",
                    feedback=None,
                    metadata={"line": line[:400]},
                )
                count += 1
            return count

        return count

    def _ingest_jsonl_log(self, source_id: str, path: Path) -> int:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-200:]
        except Exception:
            return 0
        count = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            self.record_event(
                source=source_id,
                intent="runtime_history",
                action="ingest_json_log",
                result=parsed.get("level", "loaded"),
                confidence=0.75,
                reason=parsed.get("reason") or parsed.get("msg", "Parsed Bolt log"),
                feedback=None,
                metadata={"file": str(path), "event": parsed},
            )
            count += 1
        return count

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
        entry = {
            "timestamp": _now_iso(),
            "source": source,
            "intent": intent,
            "action": action,
            "result": result,
            "confidence": round(float(confidence), 3),
            "reason": reason,
            "feedback": feedback,
            "metadata": metadata or {},
        }
        _append_jsonl(UNIFIED_MEMORY_FILE, entry)

    # ----------------------------------- Think ---------------------------------
    def think(self, current_context: Dict[str, Any]) -> Dict[str, Any]:
        memories = self._load_recent_memory(100)
        game = current_context.get("game", "Gaming")
        options = [
            "Queue only high-confidence clips",
            "Ask for title refinement before queueing",
            "Skip low-scoring clips and store for archive",
        ]
        tradeoffs = [
            "Higher confidence threshold increases quality but lowers output volume.",
            "Manual confirmation improves control but reduces automation speed.",
            "Aggressive skipping protects brand quality but may miss experimental winners.",
        ]
        recommendation = "Queue top clips above score floor with assistive confirmation."
        if any((m.get("feedback") or "").lower().startswith("reject") for m in memories):
            recommendation = "Present fewer, higher-confidence options due to recent rejections."
        return {
            "situation": f"Bolt processing {current_context.get('recording', 'session')} for {game}",
            "options": options,
            "tradeoffs": tradeoffs,
            "recommended_next_step": recommendation,
            "memory_signals_used": len(memories),
        }

    def _load_recent_memory(self, limit: int) -> List[Dict[str, Any]]:
        if not UNIFIED_MEMORY_FILE.exists():
            return []
        try:
            lines = UNIFIED_MEMORY_FILE.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    # ---------------------------------- Decide ---------------------------------
    def propose_actions(self, candidates: List[Dict[str, Any]]) -> List[ProposedAction]:
        proposed: List[ProposedAction] = []
        for idx, candidate in enumerate(candidates, start=1):
            action = candidate.get("action", "queue_clip")
            score = float(candidate.get("score", 0))
            recency = 1.0
            success_rate = self._success_rate_for(action)
            feedback = self._feedback_bias_for(action)
            weights = self.model.get("weights", {})
            confidence = (
                (min(100.0, score) / 100.0) * 0.4
                + recency * float(weights.get("recency", 0.25))
                + success_rate * float(weights.get("success_rate", 0.45))
                + feedback * float(weights.get("feedback", 0.30))
            )
            confidence = max(0.0, min(0.99, confidence))
            risk = "high" if action in {"delete_clip", "publish_now"} else "low"
            reason = (
                f"Score={score:.1f}, success_rate={success_rate:.2f}, "
                f"feedback_bias={feedback:.2f}"
            )
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

    def confirm_action(self, proposal: ProposedAction) -> bool:
        if proposal.risk == "high":
            return False
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
            if proposal.get("action_id") == action_id and item.get("status") == "pending":
                item["status"] = "approved" if approved else "rejected"
                item["resolved_at"] = _now_iso()
                item["note"] = note
                self.learn_from_feedback(
                    proposal.get("action", "queue_clip"),
                    accepted=approved,
                    feedback_text=note or ("approved_in_batch" if approved else "rejected_in_batch"),
                )
                self.audit(
                    "pending_resolution",
                    {"action_id": action_id, "approved": approved, "note": note},
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
            if item.get("status") != "approved":
                continue
            if item.get("applied_at"):
                continue
            proposal = item.get("proposal", {})
            ok = self._execute_proposal(proposal)
            item["applied_at"] = _now_iso()
            item["apply_result"] = "success" if ok else "failed"
            applied_count += 1 if ok else 0
            self.audit("apply_approved", {"proposal": proposal, "success": ok})
            self.learn_from_outcome(
                proposal.get("action", "queue_clip"),
                success=ok,
                details={"proposal": proposal},
            )
        _safe_write_json(PENDING_PROPOSALS_FILE, pending)
        return applied_count

    def _execute_proposal(self, proposal: Dict[str, Any]) -> bool:
        action = proposal.get("action", "")
        payload = proposal.get("payload", {})
        if action != "queue_clip":
            return False
        clip_path = payload.get("clip_path")
        if not clip_path:
            return False
        try:
            from pathlib import Path as _Path

            style = payload.get("style", "letterbox")
            vertical = _format_for_tiktok(clip_path, style=style)
            title = payload.get("title") or _Path(clip_path).stem.replace("_", " ")
            hashtags = payload.get("hashtags") or []
            score = float(payload.get("score", 50))
            _add_to_queue(clip_path=vertical, title=title, hashtags=hashtags, score=score)
            return True
        except Exception:
            return False

    def _success_rate_for(self, action: str) -> float:
        outcomes = self.model.get("outcomes_by_action", {}).get(action, {"ok": 0, "total": 0})
        total = float(outcomes.get("total", 0))
        if total <= 0:
            return 0.5
        return max(0.0, min(1.0, float(outcomes.get("ok", 0)) / total))

    def _feedback_bias_for(self, action: str) -> float:
        score = float(self.model.get("feedback_by_action", {}).get(action, 0.0))
        normalized = (score + 5.0) / 10.0
        return max(0.0, min(1.0, normalized))

    # ----------------------------------- Learn ---------------------------------
    def learn_from_feedback(self, action: str, accepted: bool, feedback_text: str = "") -> None:
        adjustment = 1.0 if accepted else -1.0
        feedback_map = self.model.setdefault("feedback_by_action", {})
        feedback_map[action] = float(feedback_map.get(action, 0.0)) + adjustment

        self.record_event(
            source="decision_feedback",
            intent="user_preference",
            action=action,
            result="accepted" if accepted else "rejected",
            confidence=0.9,
            reason="User confirmation feedback recorded",
            feedback=feedback_text or ("accepted" if accepted else "rejected"),
            metadata={},
        )
        _safe_write_json(DECISION_MODEL_FILE, self.model)

    def learn_from_outcome(self, action: str, success: bool, details: Dict[str, Any]) -> None:
        outcomes = self.model.setdefault("outcomes_by_action", {})
        stats = outcomes.setdefault(action, {"ok": 0, "total": 0})
        stats["total"] = int(stats.get("total", 0)) + 1
        if success:
            stats["ok"] = int(stats.get("ok", 0)) + 1
        self.record_event(
            source="decision_outcome",
            intent="execution_result",
            action=action,
            result="success" if success else "failed",
            confidence=0.95,
            reason="Action execution outcome captured",
            feedback=None,
            metadata=details,
        )
        _safe_write_json(DECISION_MODEL_FILE, self.model)

    # ------------------------------ Safety + audit ------------------------------
    def enforce_action_policy(self, proposal: ProposedAction) -> bool:
        allowlist = set(self.config.get("decision_allowlist", ["queue_clip"]))
        denylist = set(self.config.get("decision_denylist", ["delete_clip", "publish_now"]))
        if proposal.action in denylist:
            return False
        return proposal.action in allowlist

    def audit(self, phase: str, payload: Dict[str, Any]) -> None:
        line = {
            "timestamp": _now_iso(),
            "phase": phase,
            "payload": payload,
        }
        _append_jsonl(AUDIT_LOG_FILE, line)


def sys_stdin_interactive() -> bool:
    try:
        return os.isatty(0)
    except Exception:
        return False


def review_pending_cli() -> int:
    engine = ThinkLearnDecideEngine({})
    pending = [p for p in engine.pending_proposals() if p.get("status") == "pending"]
    if not pending:
        print("No pending proposals.")
        return 0

    print(f"Pending proposals: {len(pending)}")
    for idx, item in enumerate(pending, start=1):
        proposal = item.get("proposal", {})
        print(
            f"{idx}. {proposal.get('action_id')} | {proposal.get('action')} | "
            f"confidence={proposal.get('confidence')} | clip={proposal.get('payload', {}).get('clip_path', '-')}"
        )

    if not sys_stdin_interactive():
        print("Non-interactive mode: run this command in a terminal to approve/reject.")
        return 1

    choice = input("Approve all pending proposals? [y/N]: ").strip().lower()
    approve_all = choice in {"y", "yes"}
    for item in pending:
        proposal = item.get("proposal", {})
        action_id = proposal.get("action_id", "")
        if not action_id:
            continue
        if approve_all:
            engine.resolve_pending(action_id, approved=True, note="approved_all_batch")
            continue
        answer = input(f"Approve {action_id}? [y/N]: ").strip().lower()
        engine.resolve_pending(action_id, approved=answer in {"y", "yes"}, note="manual_batch_review")
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
    print("Usage: python -m modules.Think_Learn_Decide --review-pending|--apply-approved")
