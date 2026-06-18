#!/usr/bin/env python3
"""
modules/Memory_Index.py
=======================
Local memory retrieval for Bolt.

This is the first step toward a vector store without adding a heavy service.
It builds a searchable JSON index from Bolt's Markdown memory, decision logs,
and clip history, stores a lightweight hashed vector per entry, then ranks
results with cosine similarity plus a keyword safety net.

Why start here:
- It is local and easy to debug.
- It works without API keys or model downloads.
- It creates a stable interface that can later be backed by embeddings.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

MEMORY_INDEX_FILE = DATA_DIR / "memory_index.json"
UNIFIED_MEMORY_FILE = DATA_DIR / "unified_memory.jsonl"
PROCESSED_RECORDINGS_FILE = DATA_DIR / "processed_recordings.json"
SEEN_CLIPS_FILE = PROJECT_ROOT / "seen_clips.json"
DECISION_AUDIT_FILE = LOGS_DIR / "decision_audit.log"
PERFORMANCE_OUTCOMES_FILE = DATA_DIR / "performance_outcomes.jsonl"
VECTOR_DIMENSIONS = 256

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "his",
    "i",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "so",
    "that",
    "the",
    "this",
    "to",
    "was",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "you",
    "your",
}

SUPPORTIVE_TERMS = {
    "approved",
    "queue",
    "queued",
    "success",
    "successful",
    "worked",
    "strong",
    "ready",
    "posted",
    "performed",
    "useful",
    "keep",
}

CAUTIONARY_TERMS = {
    "reject",
    "rejected",
    "blocked",
    "failed",
    "discard",
    "below",
    "skip",
    "skipped",
    "underperformed",
    "caution",
    "avoid",
    "stale",
}


@dataclass
class MemoryEntry:
    id: str
    source: str
    kind: str
    title: str
    text: str
    tags: List[str]
    updated_at: str
    metadata: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "tags": self.tags,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _safe_load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9_']+", text.lower())
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def _searchable_text(entry: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("text") or ""),
            " ".join(str(tag) for tag in entry.get("tags", [])),
        ]
    )


def _token_hash(token: str, dimensions: int = VECTOR_DIMENSIONS) -> int:
    # Stable hash without relying on Python's randomized hash().
    value = 2166136261
    for char in token:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return value % dimensions


def _vectorize_text(text: str, dimensions: int = VECTOR_DIMENSIONS) -> List[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * dimensions

    counts = Counter(tokens)
    vector = [0.0] * dimensions
    total = sum(counts.values()) or 1
    for token, count in counts.items():
        # Log-scaled term frequency keeps repeated log boilerplate from winning.
        vector[_token_hash(token, dimensions)] += 1.0 + math.log(count / total + 1.0)

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "entry"


def _summarize(text: str, limit: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _matched_terms(query_tokens: Counter, entry: Dict[str, Any]) -> List[str]:
    entry_tokens = set(_tokenize(_searchable_text(entry)))
    return sorted(token for token in query_tokens if token in entry_tokens)


def _classify_memory_signal(
    entry: Dict[str, Any], matched: List[str]
) -> Dict[str, Any]:
    searchable = _searchable_text(entry).lower()
    tags = {str(tag).lower() for tag in entry.get("tags", [])}

    positive_hits = sorted(
        term for term in SUPPORTIVE_TERMS if term in searchable or term in tags
    )
    caution_hits = sorted(
        term for term in CAUTIONARY_TERMS if term in searchable or term in tags
    )

    if caution_hits and not positive_hits:
        signal = "cautionary"
        reason = f"caution terms: {', '.join(caution_hits[:3])}"
    elif positive_hits and not caution_hits:
        signal = "supportive"
        reason = f"supportive terms: {', '.join(positive_hits[:3])}"
    elif positive_hits and caution_hits:
        signal = "mixed"
        reason = f"mixed terms: +{', '.join(positive_hits[:2])}; -{', '.join(caution_hits[:2])}"
    else:
        signal = "context"
        reason = "context match"

    return {
        "signal": signal,
        "signal_reason": reason,
        "matched_terms": matched,
    }


def _dedupe_key(entry: Dict[str, Any]) -> str:
    text = str(entry.get("text") or "")
    return "|".join(
        [
            str(entry.get("source") or ""),
            str(entry.get("title") or ""),
            _slug(_summarize(text, limit=160)),
        ]
    )


def _file_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            timespec="seconds"
        )
    except Exception:
        return _now_iso()


def _split_markdown_sections(path: Path, root: Path) -> List[MemoryEntry]:
    text = _safe_read_text(path)
    if not text:
        return []

    rel = path.relative_to(root).as_posix()
    sections: List[MemoryEntry] = []
    current_title = path.stem
    current_lines: List[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if not body:
            return
        tags = ["markdown", *path.relative_to(MEMORY_DIR).parts[:-1]]
        sections.append(
            MemoryEntry(
                id=f"{rel}#{_slug(current_title)}",
                source=rel,
                kind="markdown",
                title=current_title,
                text=body,
                tags=[tag for tag in tags if tag],
                updated_at=_file_mtime(path),
                metadata={"path": str(path)},
            )
        )

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            current_title = line.lstrip("#").strip() or path.stem
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()

    if sections:
        return sections

    return [
        MemoryEntry(
            id=f"{rel}#full",
            source=rel,
            kind="markdown",
            title=path.stem,
            text=text,
            tags=["markdown"],
            updated_at=_file_mtime(path),
            metadata={"path": str(path)},
        )
    ]


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            yield payload


def _entries_from_unified_memory(root: Path) -> List[MemoryEntry]:
    entries: List[MemoryEntry] = []
    if not UNIFIED_MEMORY_FILE.exists():
        return entries

    for idx, item in enumerate(_iter_jsonl(UNIFIED_MEMORY_FILE), start=1):
        reason = str(item.get("reason") or "")
        metadata = (
            item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        )
        preview = str(metadata.get("preview") or "")
        clip_path = str(
            metadata.get("clip_path") or metadata.get("recording_path") or ""
        )
        feedback = str(item.get("feedback") or "")
        text = "\n".join(
            part for part in [reason, preview, clip_path, feedback] if part
        ).strip()
        if not text:
            continue

        action = str(item.get("action") or "event")
        intent = str(item.get("intent") or "")
        source = str(item.get("source") or "unknown")
        timestamp = str(item.get("timestamp") or _now_iso())
        entries.append(
            MemoryEntry(
                id=f"data/unified_memory.jsonl#{idx}",
                source="data/unified_memory.jsonl",
                kind="decision_event",
                title=f"{action}: {reason or source}",
                text=text,
                tags=[
                    tag for tag in ["decision", "event", source, intent, action] if tag
                ],
                updated_at=timestamp,
                metadata=item,
            )
        )
    return entries


def _entries_from_clip_history(root: Path) -> List[MemoryEntry]:
    entries: List[MemoryEntry] = []
    seen = _safe_load_json(SEEN_CLIPS_FILE, [])
    processed = _safe_load_json(PROCESSED_RECORDINGS_FILE, [])

    for idx, clip in enumerate(seen if isinstance(seen, list) else [], start=1):
        clip_name = str(clip)
        entries.append(
            MemoryEntry(
                id=f"seen_clips.json#{idx}",
                source="seen_clips.json",
                kind="clip",
                title=Path(clip_name).name,
                text=f"Seen clip: {clip_name}",
                tags=["clip", "seen"],
                updated_at=_file_mtime(SEEN_CLIPS_FILE),
                metadata={"clip": clip_name},
            )
        )

    for idx, recording in enumerate(
        processed if isinstance(processed, list) else [], start=1
    ):
        recording_name = str(recording)
        entries.append(
            MemoryEntry(
                id=f"data/processed_recordings.json#{idx}",
                source="data/processed_recordings.json",
                kind="recording",
                title=Path(recording_name).name,
                text=f"Processed recording: {recording_name}",
                tags=["recording", "processed"],
                updated_at=_file_mtime(PROCESSED_RECORDINGS_FILE),
                metadata={"recording": recording_name},
            )
        )
    return entries


def _entries_from_decision_audit(root: Path) -> List[MemoryEntry]:
    entries: List[MemoryEntry] = []
    if not DECISION_AUDIT_FILE.exists():
        return entries

    for idx, item in enumerate(_iter_jsonl(DECISION_AUDIT_FILE), start=1):
        phase = str(item.get("phase") or "audit")
        payload = item.get("payload", {})
        text = (
            json.dumps(payload, sort_keys=True)
            if isinstance(payload, dict)
            else str(payload)
        )
        if not text:
            continue
        entries.append(
            MemoryEntry(
                id=f"logs/decision_audit.log#{idx}",
                source="logs/decision_audit.log",
                kind="decision_audit",
                title=f"Decision audit: {phase}",
                text=text,
                tags=["decision", "audit", phase],
                updated_at=str(item.get("timestamp") or _now_iso()),
                metadata=item,
            )
        )
    return entries


def _entries_from_performance_outcomes(root: Path) -> List[MemoryEntry]:
    entries: List[MemoryEntry] = []
    if not PERFORMANCE_OUTCOMES_FILE.exists():
        return entries

    for idx, item in enumerate(_iter_jsonl(PERFORMANCE_OUTCOMES_FILE), start=1):
        game = str(item.get("game") or "Gaming")
        trigger = str(item.get("trigger") or "highlight")
        clip_path = str(item.get("clip_path") or "")
        views = int(item.get("views") or 0)
        likes = int(item.get("likes") or 0)
        success = bool(item.get("success"))
        title = f"Clip performance: {trigger} for {game}"
        text = (
            f"Posted clip outcome for {game}: trigger={trigger}, "
            f"views={views}, likes={likes}, success={success}, clip={clip_path}. "
            f"{item.get('note', '')}"
        ).strip()
        entries.append(
            MemoryEntry(
                id=f"data/performance_outcomes.jsonl#{idx}",
                source="data/performance_outcomes.jsonl",
                kind="performance_outcome",
                title=title,
                text=text,
                tags=[
                    "performance",
                    "outcome",
                    "clip",
                    game,
                    trigger,
                    "success" if success else "underperformed",
                ],
                updated_at=str(item.get("timestamp") or _now_iso()),
                metadata=item,
            )
        )
    return entries


def build_memory_entries(project_root: Path = PROJECT_ROOT) -> List[MemoryEntry]:
    entries: List[MemoryEntry] = []
    memory_dir = project_root / "memory"

    if memory_dir.exists():
        for md_file in sorted(memory_dir.rglob("*.md")):
            entries.extend(_split_markdown_sections(md_file, project_root))

    entries.extend(_entries_from_unified_memory(project_root))
    entries.extend(_entries_from_clip_history(project_root))
    entries.extend(_entries_from_decision_audit(project_root))
    entries.extend(_entries_from_performance_outcomes(project_root))
    return entries


def refresh_memory_index(
    project_root: Path = PROJECT_ROOT, out_file: Path = MEMORY_INDEX_FILE
) -> Dict[str, Any]:
    entries = build_memory_entries(project_root)
    entry_payloads = []
    for entry in entries:
        payload_entry = entry.as_dict()
        payload_entry["vector"] = _vectorize_text(_searchable_text(payload_entry))
        entry_payloads.append(payload_entry)

    payload = {
        "generated_at": _now_iso(),
        "version": 2,
        "vector": {
            "type": "hashed_term_frequency",
            "dimensions": VECTOR_DIMENSIONS,
        },
        "entry_count": len(entries),
        "entries": entry_payloads,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_memory_index(
    index_file: Path = MEMORY_INDEX_FILE, auto_refresh: bool = True
) -> Dict[str, Any]:
    if not index_file.exists() and auto_refresh:
        return refresh_memory_index(out_file=index_file)
    return _safe_load_json(index_file, {"entries": []})


def _score_entry(query_tokens: Counter, entry: Dict[str, Any]) -> float:
    searchable = _searchable_text(entry)
    entry_tokens = Counter(_tokenize(searchable))
    if not query_tokens or not entry_tokens:
        return 0.0

    overlap = sum(
        min(weight, entry_tokens[token]) for token, weight in query_tokens.items()
    )
    if overlap == 0:
        return 0.0

    length_penalty = math.sqrt(sum(entry_tokens.values())) or 1.0
    tag_bonus = 0.15 * sum(
        1 for token in query_tokens if token in set(entry.get("tags", []))
    )
    title_bonus = 0.25 * sum(
        1 for token in query_tokens if token in _tokenize(str(entry.get("title") or ""))
    )
    return (overlap / length_penalty) + tag_bonus + title_bonus


def _hybrid_score(
    query: str, query_tokens: Counter, query_vector: List[float], entry: Dict[str, Any]
) -> float:
    vector = entry.get("vector")
    vector_score = (
        _cosine_similarity(query_vector, vector) if isinstance(vector, list) else 0.0
    )
    keyword_score = _score_entry(query_tokens, entry)

    # Normalize the older token score into a smaller boost. Exact words still
    # matter, but vector similarity carries the main ranking.
    keyword_boost = min(keyword_score, 1.0) * 0.35
    recency_boost = (
        0.03
        if str(entry.get("updated_at") or "").startswith(
            datetime.now().strftime("%Y-%m")
        )
        else 0.0
    )
    return vector_score + keyword_boost + recency_boost


def retrieve_memory(
    query: str,
    limit: int = 5,
    kinds: Optional[List[str]] = None,
    index_file: Path = MEMORY_INDEX_FILE,
    auto_refresh: bool = True,
    dedupe: bool = True,
) -> List[Dict[str, Any]]:
    index = load_memory_index(index_file=index_file, auto_refresh=auto_refresh)
    allowed_kinds = set(kinds or [])
    query_tokens = Counter(_tokenize(query))
    query_vector = _vectorize_text(query)
    results: List[Dict[str, Any]] = []

    seen_keys = set()

    for entry in index.get("entries", []):
        if allowed_kinds and entry.get("kind") not in allowed_kinds:
            continue
        score = _hybrid_score(query, query_tokens, query_vector, entry)
        if score <= 0:
            continue
        key = _dedupe_key(entry)
        if dedupe and key in seen_keys:
            continue
        seen_keys.add(key)
        result = dict(entry)
        result["score"] = round(score, 4)
        result.pop("vector", None)
        result["summary"] = _summarize(str(entry.get("text") or ""))
        matched = _matched_terms(query_tokens, entry)
        result.update(_classify_memory_signal(entry, matched))
        results.append(result)

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(1, int(limit))]


def format_retrieved_context(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "(no relevant memory found)"

    chunks = []
    for item in results:
        chunks.append(
            "\n".join(
                [
                    f"### {item.get('title', 'Memory')}",
                    f"- source: {item.get('source')}",
                    f"- kind: {item.get('kind')}",
                    f"- score: {item.get('score')}",
                    str(item.get("summary") or item.get("text") or ""),
                ]
            )
        )
    return "\n\n".join(chunks)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build and query Bolt's local memory index."
    )
    parser.add_argument(
        "query", nargs="*", help="Optional query to search after refreshing."
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh data/memory_index.json."
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of retrieval results."
    )
    args = parser.parse_args()

    if args.refresh or not MEMORY_INDEX_FILE.exists():
        payload = refresh_memory_index()
        print(f"Indexed {payload['entry_count']} memory entries -> {MEMORY_INDEX_FILE}")

    if args.query:
        hits = retrieve_memory(" ".join(args.query), limit=args.limit)
        print(format_retrieved_context(hits))
