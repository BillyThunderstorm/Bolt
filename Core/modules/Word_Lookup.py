#!/usr/bin/env python3
"""
Word_Lookup.py — dictionary, spellcheck, and thesaurus (READY)
==============================================================
Local-first writing helper for titles, captions, and reviews.

  Spellcheck  — /usr/share/dict/words + Data/word_extras.txt (offline)
  Dictionary  — Free Dictionary API (no key; network; soft-fail)
  Thesaurus   — Datamuse (no key; network; soft-fail)

Soft-fail prefix: ``Word lookup unavailable:``. Local spelling still
works when the network is down. Distinct from READY ``bolt search``
(DuckDuckGo).

Public API:
  status() / list_items() / print_status()
  lookup() / define() / spell() / synonyms() / antonyms() / check_text()
  spoken_lookup() / spoken_spell() / spoken_syn()
  closest_in() / repair_tokens()  — typo hear-through for CLI + conversation
  main()
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_SOFT = "Word lookup unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_EXTRAS_FILE = _REPO / "Data" / "word_extras.txt"
_DICT_PATHS = (
    Path("/usr/share/dict/words"),
    Path("/usr/share/dict/web2"),
    Path("/usr/dict/words"),
)
_DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
_DATAMUSE = "https://api.datamuse.com/words"
_UA = "Bolt/word-lookup (local-first creator assistant)"
_HTTP_TIMEOUT = 6.0
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# Creator / product terms the system word list often misses.
_BUILTIN_EXTRAS = {
    "tiktok",
    "twitch",
    "youtube",
    "shorts",
    "vod",
    "vods",
    "simplybilly",
    "billy",
    "william",
    "randy",
    "bolt",
    "grok",
    "ollama",
    "nexus",
    "obs",
    "ffmpeg",
    "streamlabs",
    "streamdeck",
    "nvidia",
    "logitech",
    "gameplay",
    "streamer",
    "asin",
    "skincare",
    "storefront",
    "affiliate",
    "supergrok",
    "chatgpt",
    "huggingface",
    "chromadb",
    "yt-dlp",
    "handbrake",
    "tesseract",
    "rumps",
    "aitum",
    "thunderstone",
}

_WORDS: Optional[Set[str]] = None
_WORD_SOURCE = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _load_extras_file(path: Path) -> Set[str]:
    out: Set[str] = set()
    if not path.is_file():
        return out
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            token = _normalize_word(line)
            if token:
                out.add(token)
    except Exception:
        return out
    return out


def _word_list() -> Tuple[Set[str], str]:
    """Load system dictionary + extras once. Returns (set, source path)."""
    global _WORDS, _WORD_SOURCE
    if _WORDS is not None:
        return _WORDS, _WORD_SOURCE

    words: Set[str] = set(_BUILTIN_EXTRAS)
    source = "builtin extras"
    for path in _DICT_PATHS:
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    token = line.strip().lower()
                    if token and token.isascii() and token.isalpha():
                        words.add(token)
            source = str(path)
            break
        except Exception:
            continue
    extras = _load_extras_file(_EXTRAS_FILE)
    if extras:
        words.update(extras)
        if source == "builtin extras":
            source = str(_EXTRAS_FILE)
        else:
            source = f"{source} + extras"
    _WORDS = words
    _WORD_SOURCE = source
    return _WORDS, _WORD_SOURCE


def _normalize_word(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.strip("\"'`.,;:!?()[]{}")
    if t.endswith("'s") and len(t) > 3:
        t = t[:-2]
    t = t.strip("-'")
    return t


def _edits1(word: str) -> Set[str]:
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [left + right[1:] for left, right in splits if right]
    transposes = [
        left + right[1] + right[0] + right[2:]
        for left, right in splits
        if len(right) > 1
    ]
    replaces = [
        left + ch + right[1:]
        for left, right in splits
        if right
        for ch in _LETTERS
    ]
    inserts = [left + ch + right for left, right in splits for ch in _LETTERS]
    return set(deletes + transposes + replaces + inserts)


def _suggestions(word: str, words: Set[str], *, limit: int = 8) -> List[str]:
    """Peter Norvig-style local suggestions (edit distance 1, then 2)."""
    if not word or len(word) > 24:
        return []
    known1 = [w for w in _edits1(word) if w in words]
    if known1:
        known1.sort(key=lambda w: (abs(len(w) - len(word)), w))
        return known1[:limit]
    known2: Set[str] = set()
    for edit in _edits1(word):
        if len(edit) > 24:
            continue
        for w in _edits1(edit):
            if w in words:
                known2.add(w)
        if len(known2) >= limit * 4:
            break
    ranked = sorted(known2, key=lambda w: (abs(len(w) - len(word)), w))
    return ranked[:limit]


def _fold_token(text: str) -> str:
    return (text or "").lower().replace("_", "").replace("-", "")


def damerau_levenshtein(a: str, b: str) -> int:
    """Damerau–Levenshtein distance (insert, delete, replace, transpose)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev_prev = [0] * (lb + 1)
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        row = [i] + [0] * lb
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            val = prev[j] + 1
            ins = row[j - 1] + 1
            sub = prev[j - 1] + cost
            if ins < val:
                val = ins
            if sub < val:
                val = sub
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                transp = prev_prev[j - 2] + 1
                if transp < val:
                    val = transp
            row[j] = val
        prev_prev, prev = prev, row
    return prev[lb]


def closest_in(
    token: str,
    candidates: Sequence[str],
    *,
    limit: int = 3,
    max_dist: int = 2,
) -> List[Tuple[str, int]]:
    """Closest known names for a typed token (commands, intent words).

    Hyphens/underscores fold so ``clipdedupe`` matches ``clip-dedupe``.
    Distance 0 = exact or fold-equal. Never raises.
    """
    raw = (token or "").strip()
    if not raw or not candidates:
        return []
    lowered = raw.lower()
    folded = _fold_token(raw)
    exact: List[Tuple[str, int]] = []
    folded_hits: List[Tuple[str, int]] = []
    near: List[Tuple[int, int, str]] = []
    seen: Set[str] = set()
    for cand in candidates:
        name = str(cand or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cfold = _fold_token(name)
        if key == lowered or name.replace("_", "-") == raw.replace("_", "-"):
            exact.append((name, 0))
            continue
        if cfold and cfold == folded:
            folded_hits.append((name, 0))
            continue
        if abs(len(cfold) - len(folded)) > max_dist:
            continue
        dist = damerau_levenshtein(folded, cfold)
        if dist <= max_dist:
            near.append((dist, abs(len(cfold) - len(folded)), name))
    if exact:
        return exact[:limit]
    if folded_hits:
        return folded_hits[:limit]
    near.sort()
    return [(name, dist) for dist, _, name in near[:limit]]


def repair_tokens(
    text: str,
    vocab: Sequence[str],
    *,
    max_dist: int = 2,
    skip_known_words: bool = True,
) -> Tuple[str, List[Tuple[str, str]]]:
    """Rewrite a phrase toward ``vocab`` when a token is uniquely close.

    Real dictionary words are left alone (so ``weak`` does not become ``week``)
    unless they already sit in the vocab. Returns ``(text, [(from, to), ...])``.
    """
    raw = (text or "").strip()
    if not raw or not vocab:
        return raw, []
    vocab_list = [str(v).strip() for v in vocab if str(v).strip()]
    vocab_fold = {_fold_token(v) for v in vocab_list if _fold_token(v)}
    parts = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", raw)
    changes: List[Tuple[str, str]] = []
    out: List[str] = []
    for part in parts:
        if not part[0].isalpha():
            out.append(part)
            continue
        token = part.lower()
        if _fold_token(token) in vocab_fold:
            out.append(part)
            continue
        hits = closest_in(token, vocab_list, limit=2, max_dist=max_dist)
        if not hits:
            out.append(part)
            continue
        best, dist = hits[0]
        unique = len(hits) == 1 or (len(hits) > 1 and hits[1][1] > dist)
        if not unique or dist < 1:
            out.append(part)
            continue
        if dist == 2 and len(_fold_token(token)) < 6:
            out.append(part)
            continue
        if skip_known_words:
            try:
                spelled = spell(token)
            except Exception:
                spelled = {"ok": False}
            if spelled.get("ok"):
                out.append(part)
                continue
        replacement = best
        if part[0].isupper() and len(part) > 1 and part[1:].islower():
            replacement = best[:1].upper() + best[1:]
        elif part.isupper():
            replacement = best.upper()
        out.append(replacement)
        changes.append((part, replacement))
    return "".join(out), changes


def _http_json(url: str, timeout: float = _HTTP_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return None
    return json.loads(raw)


def _datamuse(rel: str, word: str, *, max_n: int = 12) -> List[str]:
    q = urllib.parse.urlencode({rel: word, "max": str(max_n)})
    url = f"{_DATAMUSE}?{q}"
    data = _http_json(url)
    if not isinstance(data, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        w = str(row.get("word") or "").strip().lower()
        if not w or w == word or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


_POS = {
    "adj": "adjective",
    "n": "noun",
    "v": "verb",
    "adv": "adverb",
    "u": "",
}


def _datamuse_define(word: str) -> Dict[str, Any]:
    """Datamuse ``md=d`` definitions (same host as the thesaurus)."""
    q = urllib.parse.urlencode({"sp": word, "md": "d", "max": "1"})
    try:
        data = _http_json(f"{_DATAMUSE}?{q}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "found": False,
                "definitions": [],
                "phonetic": "",
                "synonyms": [],
                "antonyms": [],
                "error": "",
            }
        raise
    defs: List[Dict[str, str]] = []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for raw in data[0].get("defs") or []:
            line = str(raw).strip()
            if not line:
                continue
            if "\t" in line:
                tag, text = line.split("\t", 1)
            else:
                tag, text = "", line
            text = text.strip()
            if not text:
                continue
            defs.append(
                {
                    "pos": _POS.get(tag.strip().lower(), tag.strip()),
                    "definition": text,
                    "example": "",
                }
            )
    return {
        "found": bool(defs),
        "definitions": defs,
        "phonetic": "",
        "synonyms": [],
        "antonyms": [],
        "error": "",
    }


def _dictionaryapi_define(word: str) -> Dict[str, Any]:
    """dictionaryapi.dev — phonetics/examples when it answers in time."""
    url = _DICT_API.format(word=urllib.parse.quote(word))
    try:
        data = _http_json(url, timeout=3.0)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"found": False, "definitions": [], "phonetic": "", "error": ""}
        raise
    if not isinstance(data, list) or not data:
        return {"found": False, "definitions": [], "phonetic": "", "error": ""}

    phonetic = ""
    defs: List[Dict[str, str]] = []
    syns: List[str] = []
    ants: List[str] = []
    seen_syn: Set[str] = set()
    seen_ant: Set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not phonetic:
            phonetic = str(entry.get("phonetic") or "").strip()
            if not phonetic:
                for ph in entry.get("phonetics") or []:
                    if isinstance(ph, dict) and ph.get("text"):
                        phonetic = str(ph["text"]).strip()
                        break
        for meaning in entry.get("meanings") or []:
            if not isinstance(meaning, dict):
                continue
            pos = str(meaning.get("partOfSpeech") or "").strip()
            for syn in meaning.get("synonyms") or []:
                s = str(syn).strip().lower()
                if s and s not in seen_syn:
                    seen_syn.add(s)
                    syns.append(s)
            for ant in meaning.get("antonyms") or []:
                a = str(ant).strip().lower()
                if a and a not in seen_ant:
                    seen_ant.add(a)
                    ants.append(a)
            for item in meaning.get("definitions") or []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("definition") or "").strip()
                if not text:
                    continue
                defs.append(
                    {
                        "pos": pos,
                        "definition": text,
                        "example": str(item.get("example") or "").strip(),
                    }
                )
                for syn in item.get("synonyms") or []:
                    s = str(syn).strip().lower()
                    if s and s not in seen_syn:
                        seen_syn.add(s)
                        syns.append(s)
                for ant in item.get("antonyms") or []:
                    a = str(ant).strip().lower()
                    if a and a not in seen_ant:
                        seen_ant.add(a)
                        ants.append(a)
    return {
        "found": bool(defs),
        "definitions": defs,
        "phonetic": phonetic,
        "synonyms": syns,
        "antonyms": ants,
        "error": "",
    }


def _define_remote(word: str) -> Dict[str, Any]:
    """Datamuse first (reliable); dictionaryapi.dev adds phonetic/examples."""
    error = ""
    primary: Dict[str, Any] = {
        "found": False,
        "definitions": [],
        "phonetic": "",
        "synonyms": [],
        "antonyms": [],
        "error": "",
    }
    try:
        primary = _datamuse_define(word)
    except urllib.error.HTTPError as exc:
        error = _soft(f"dictionary HTTP {exc.code}")
    except Exception as exc:
        error = _soft(f"dictionary failed ({exc})")

    extra: Dict[str, Any] = {}
    try:
        extra = _dictionaryapi_define(word)
    except Exception:
        extra = {}

    defs = list(primary.get("definitions") or [])
    if extra.get("definitions") and not defs:
        defs = list(extra["definitions"])
    elif extra.get("definitions"):
        # Prefer Datamuse text; keep dictionaryapi examples when the gloss matches.
        by_text = {d.get("definition"): d for d in extra["definitions"]}
        for item in defs:
            other = by_text.get(item.get("definition") or "")
            if other and other.get("example") and not item.get("example"):
                item["example"] = other["example"]
        # If Datamuse was thin, append a couple of extra glosses.
        seen = {d.get("definition") for d in defs}
        for item in extra["definitions"]:
            if item.get("definition") in seen:
                continue
            defs.append(item)
            if len(defs) >= 8:
                break

    syns = list(extra.get("synonyms") or [])
    ants = list(extra.get("antonyms") or [])
    phonetic = str(extra.get("phonetic") or "")
    found = bool(defs)
    if not found and error:
        return {
            "found": False,
            "definitions": [],
            "phonetic": "",
            "synonyms": syns,
            "antonyms": ants,
            "error": error,
        }
    return {
        "found": found,
        "definitions": defs,
        "phonetic": phonetic,
        "synonyms": syns,
        "antonyms": ants,
        "error": "" if found else error,
    }


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for dictionary / spellcheck / thesaurus (READY)."""
    try:
        words, source = _word_list()
        extras_present = _EXTRAS_FILE.is_file()
        dict_path = next((str(p) for p in _DICT_PATHS if p.is_file()), "")
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": bool(words),
            "partial": False,
            "readiness": "READY" if words else "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "word_count": len(words),
            "word_source": source,
            "system_dict": dict_path,
            "extras_path": str(_EXTRAS_FILE),
            "extras_present": extras_present,
            "dictionary_api": "dictionaryapi.dev",
            "thesaurus_api": "datamuse.com",
            "cli": "bolt word",
            "note": (
                "local spellcheck + free dictionary/thesaurus; "
                "not bolt search (DuckDuckGo)"
            ),
            "is_stranger_ready": bool(words),
            "probe": bool(probe),
            "network_ok": None,
            "error": "",
            "hint": "",
        }
        if not words:
            out["error"] = _soft("no local word list found")
            out["hint"] = out["error"]
            out["ready"] = False
            out["partial"] = True
            out["is_stranger_ready"] = False
            return out

        out["hint"] = (
            f"{len(words):,} words from {source} · "
            "define/syn need network (soft-fail)"
        )
        if probe:
            try:
                _http_json(_DICT_API.format(word="test"), timeout=2.5)
                out["network_ok"] = True
                out["hint"] += " · dictionary API reachable"
            except Exception as exc:
                out["network_ok"] = False
                out["hint"] += f" · dictionary API skipped ({exc})"
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "is_stranger_ready": False,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def spell(word: str) -> Dict[str, Any]:
    """Local spellcheck for one token. Never raises."""
    token = _normalize_word(word)
    words, source = _word_list()
    if not token:
        return {
            "word": "",
            "ok": False,
            "suggestions": [],
            "source": source,
            "error": _soft("need a word to check"),
        }
    if not words:
        return {
            "word": token,
            "ok": False,
            "suggestions": [],
            "source": source,
            "error": _soft("no local word list found"),
        }
    ok = token in words
    suggestions = [] if ok else _suggestions(token, words)
    return {
        "word": token,
        "ok": ok,
        "suggestions": suggestions,
        "source": source,
        "error": "",
    }


def check_text(text: str) -> Dict[str, Any]:
    """Spellcheck each alphabetic token in a phrase. Never raises."""
    raw = (text or "").strip()
    words, source = _word_list()
    tokens = [_normalize_word(t) for t in _TOKEN_RE.findall(raw)]
    tokens = [t for t in tokens if t and (len(t) > 1 or t in {"a", "i"})]
    misses: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        if token in words:
            continue
        misses.append(
            {
                "word": token,
                "suggestions": _suggestions(token, words),
            }
        )
    return {
        "text": raw,
        "checked": len(tokens),
        "misspellings": misses,
        "ok": not misses,
        "source": source,
        "error": "" if words else _soft("no local word list found"),
    }


def define(word: str) -> Dict[str, Any]:
    """Remote definition. Soft-fails when the network is down."""
    token = _normalize_word(word)
    if not token:
        return {
            "word": "",
            "found": False,
            "definitions": [],
            "phonetic": "",
            "error": _soft("need a word to define"),
        }
    remote = _define_remote(token)
    remote["word"] = token
    return remote


def synonyms(word: str) -> Dict[str, Any]:
    token = _normalize_word(word)
    if not token:
        return {
            "word": "",
            "items": [],
            "error": _soft("need a word for synonyms"),
        }
    items: List[str] = []
    error = ""
    try:
        items = _datamuse("rel_syn", token) or _datamuse("ml", token)
    except Exception as exc:
        error = _soft(f"thesaurus failed ({exc})")
    if not items and not error:
        remote = _define_remote(token)
        items = list(remote.get("synonyms") or [])
        if remote.get("error"):
            error = str(remote["error"])
    return {"word": token, "items": items[:16], "error": error}


def antonyms(word: str) -> Dict[str, Any]:
    token = _normalize_word(word)
    if not token:
        return {
            "word": "",
            "items": [],
            "error": _soft("need a word for antonyms"),
        }
    items: List[str] = []
    error = ""
    try:
        items = _datamuse("rel_ant", token)
    except Exception as exc:
        error = _soft(f"thesaurus failed ({exc})")
    if not items and not error:
        remote = _define_remote(token)
        items = list(remote.get("antonyms") or [])
        if remote.get("error"):
            error = str(remote["error"])
    return {"word": token, "items": items[:12], "error": error}


def lookup(word: str) -> Dict[str, Any]:
    """Full card: spelling + definition + synonyms + antonyms."""
    token = _normalize_word(word)
    spelled = spell(token)
    defined = define(token) if token else {
        "found": False,
        "definitions": [],
        "phonetic": "",
        "error": _soft("need a word"),
        "synonyms": [],
        "antonyms": [],
    }
    syns = list(defined.get("synonyms") or [])
    ants = list(defined.get("antonyms") or [])
    syn_err = ""
    ant_err = ""
    if token:
        extra_syn = synonyms(token)
        extra_ant = antonyms(token)
        syn_err = str(extra_syn.get("error") or "")
        ant_err = str(extra_ant.get("error") or "")
        for item in extra_syn.get("items") or []:
            if item not in syns:
                syns.append(item)
        for item in extra_ant.get("items") or []:
            if item not in ants:
                ants.append(item)
    errors = [
        e
        for e in (spelled.get("error"), defined.get("error"), syn_err, ant_err)
        if e
    ]
    return {
        "word": token,
        "spelling": spelled,
        "phonetic": defined.get("phonetic") or "",
        "definitions": defined.get("definitions") or [],
        "found": bool(defined.get("found")),
        "synonyms": syns[:16],
        "antonyms": ants[:12],
        "error": errors[0] if errors else "",
    }


def spoken_lookup(word: str) -> str:
    card = lookup(word)
    token = card.get("word") or (word or "").strip()
    if not token:
        return "Which word should I look up?"
    spelled = card.get("spelling") or {}
    if not spelled.get("ok"):
        sugg = ", ".join((spelled.get("suggestions") or [])[:3])
        if sugg:
            return f"{token} is not in the dictionary. Did you mean {sugg}?"
        if spelled.get("error"):
            return str(spelled["error"])
        return f"{token} is not in the local dictionary."
    defs = card.get("definitions") or []
    if defs:
        first = defs[0]
        pos = first.get("pos") or ""
        meaning = first.get("definition") or ""
        head = f"{token}"
        if pos:
            head = f"{token}, {pos}"
        syns = ", ".join((card.get("synonyms") or [])[:5])
        line = f"{head}: {meaning}"
        if syns:
            line += f" Close words: {syns}."
        return line
    if card.get("error"):
        return f"{token} is spelled correctly. {card['error']}"
    return f"{token} is spelled correctly. No definition came back."


def spoken_spell(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return "Which word should I spell-check?"
    tokens = _TOKEN_RE.findall(raw)
    if len(tokens) <= 1:
        result = spell(raw)
        token = result.get("word") or raw
        if result.get("ok"):
            return f"{token} is spelled correctly."
        sugg = ", ".join((result.get("suggestions") or [])[:4])
        if sugg:
            return f"{token} looks off. Try {sugg}."
        if result.get("error"):
            return str(result["error"])
        return f"{token} is not in the dictionary."
    checked = check_text(raw)
    misses = checked.get("misspellings") or []
    if not misses:
        return f"That looks fine. Checked {checked.get('checked', 0)} words."
    bits = []
    for miss in misses[:4]:
        sugg = ", ".join((miss.get("suggestions") or [])[:2])
        if sugg:
            bits.append(f"{miss['word']} maybe {sugg}")
        else:
            bits.append(str(miss["word"]))
    return "Possible misspellings: " + "; ".join(bits) + "."


def spoken_syn(word: str) -> str:
    result = synonyms(word)
    token = result.get("word") or (word or "").strip()
    if not token:
        return "Which word do you want a synonym for?"
    items = result.get("items") or []
    if items:
        return f"Other words for {token}: " + ", ".join(items[:8]) + "."
    if result.get("error"):
        return str(result["error"])
    return f"No synonyms came back for {token}."


def list_items(*, as_json: bool = False) -> int:
    try:
        info = status(probe=False)
        rows = [
            ("system word list", bool(info.get("system_dict"))),
            (f"word count ({info.get('word_count') or 0})", bool(info.get("word_count"))),
            ("creator extras (Data/word_extras.txt)", bool(info.get("extras_present"))),
            ("local spellcheck (offline)", bool(info.get("ready"))),
            ("datamuse define/thesaurus (no key)", True),
            ("dictionaryapi.dev phonetic (optional)", True),
            ("soft-fail CLI (bolt word)", True),
            ("distinct from bolt search (DuckDuckGo)", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": info.get("readiness"),
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Word lookup (READY — local spell; network define/syn)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (try: bolt word honest   |   bolt spell recieve   |   bolt thesaurus honest)")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Word lookup readiness (READY)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  words: {info.get('word_count')} · source: {info.get('word_source')}"
        )
        print(f"  extras: {info.get('extras_path')} ({'yes' if info.get('extras_present') else 'no'})")
        print(f"  note: {info.get('note')}")
        print(f"  soft_fail_prefix: {info.get('soft_fail_prefix')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def _print_spell(result: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
        return 0
    token = result.get("word") or ""
    if result.get("error") and not token:
        print(result["error"], file=sys.stderr)
        return 0
    if result.get("ok"):
        print(f"{token}")
        print("  spelling: ok")
        return 0
    print(f"{token}")
    print("  spelling: not in dictionary")
    sugg = result.get("suggestions") or []
    if sugg:
        print("  did you mean: " + ", ".join(sugg))
    elif result.get("error"):
        print(f"  → {result['error']}")
    return 0


def _print_check(result: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
        return 0
    if result.get("error") and not result.get("checked"):
        print(result["error"], file=sys.stderr)
        return 0
    misses = result.get("misspellings") or []
    print(
        f"checked {result.get('checked', 0)} words, "
        f"{len(misses)} misspelling{'s' if len(misses) != 1 else ''}"
    )
    for miss in misses:
        sugg = miss.get("suggestions") or []
        extra = f" → {', '.join(sugg)}" if sugg else ""
        print(f"  {miss.get('word')}{extra}")
    return 0


def _print_define(result: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
        return 0
    token = result.get("word") or ""
    if result.get("error") and not result.get("found"):
        print(result["error"], file=sys.stderr)
        return 0
    print(token)
    if result.get("phonetic"):
        print(f"  {result['phonetic']}")
    defs = result.get("definitions") or []
    if not defs:
        print("  no definition found")
        return 0
    for item in defs[:6]:
        pos = item.get("pos") or ""
        prefix = f"{pos}. " if pos else ""
        print(f"  {prefix}{item.get('definition')}")
        if item.get("example"):
            print(f"      e.g. {item['example']}")
    return 0


def _print_list_words(label: str, result: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
        return 0
    token = result.get("word") or ""
    items = result.get("items") or []
    print(token)
    if result.get("error") and not items:
        print(f"  → {result['error']}")
        return 0
    if not items:
        print(f"  no {label} found")
        return 0
    print(f"  {label}: " + ", ".join(items))
    return 0


def _print_lookup(card: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(card, indent=2))
        return 0
    token = card.get("word") or ""
    spelled = card.get("spelling") or {}
    print(token)
    if spelled.get("ok"):
        print("  spelling: ok")
    else:
        print("  spelling: not in dictionary")
        sugg = spelled.get("suggestions") or []
        if sugg:
            print("  did you mean: " + ", ".join(sugg))
    if card.get("phonetic"):
        print(f"  {card['phonetic']}")
    defs = card.get("definitions") or []
    if defs:
        for item in defs[:4]:
            pos = item.get("pos") or ""
            prefix = f"{pos}. " if pos else ""
            print(f"  {prefix}{item.get('definition')}")
            if item.get("example"):
                print(f"      e.g. {item['example']}")
    elif card.get("error"):
        print(f"  → {card['error']}")
    else:
        print("  no definition found")
    syns = card.get("synonyms") or []
    if syns:
        print("  synonyms: " + ", ".join(syns[:12]))
    ants = card.get("antonyms") or []
    if ants:
        print("  antonyms: " + ", ".join(ants[:8]))
    return 0


def _join_rest(parts: Sequence[str]) -> str:
    return " ".join(str(p) for p in parts if str(p).strip()).strip()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt word — dictionary, spellcheck, thesaurus (READY)

  bolt word                                    # status (default)
  bolt word status [--json] [--probe]
  bolt word list [--json]
  bolt word <word>                             # spelling + definition + synonyms
  bolt word define <word> [--json]
  bolt word spell <word|phrase> [--json]
  bolt word check "a sentence" [--json]
  bolt word syn <word> [--json]
  bolt word ant <word> [--json]

Aliases: dict, dictionary, define, spell, spellcheck, thesaurus, synonym.
Soft-fail: "Word lookup unavailable:".
Local spell uses /usr/share/dict/words + Data/word_extras.txt.
Define/syn use Datamuse (no key); dictionaryapi.dev is optional phonetic.
Distinct from bolt search (DuckDuckGo).
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    cleaned: List[str] = []
    for a in args:
        if a.startswith("-"):
            continue
        cleaned.append(a)

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    rest = _join_rest(cleaned[1:])

    if cmd in ("status", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("define", "definition", "meaning", "dict"):
        if not rest:
            print(_soft("need a word — bolt word define honest"), file=sys.stderr)
            return 0
        return _print_define(define(rest), as_json=json_out)
    if cmd in ("spell", "spellcheck", "spelling"):
        target = rest
        if not target:
            print(_soft("need a word — bolt spell recieve"), file=sys.stderr)
            return 0
        tokens = _TOKEN_RE.findall(target)
        if len(tokens) > 1:
            return _print_check(check_text(target), as_json=json_out)
        return _print_spell(spell(target), as_json=json_out)
    if cmd in ("check", "proof", "proofread"):
        if not rest:
            print(_soft('need text — bolt word check "this sentance"'), file=sys.stderr)
            return 0
        return _print_check(check_text(rest), as_json=json_out)
    if cmd in ("syn", "synonym", "synonyms", "thesaurus"):
        if not rest:
            print(_soft("need a word — bolt thesaurus honest"), file=sys.stderr)
            return 0
        return _print_list_words("synonyms", synonyms(rest), as_json=json_out)
    if cmd in ("ant", "antonym", "antonyms"):
        if not rest:
            print(_soft("need a word — bolt word ant honest"), file=sys.stderr)
            return 0
        return _print_list_words("antonyms", antonyms(rest), as_json=json_out)
    if cmd in ("lookup", "look"):
        if not rest:
            print(_soft("need a word — bolt word honest"), file=sys.stderr)
            return 0
        return _print_lookup(lookup(rest), as_json=json_out)

    # Bare word / phrase → full lookup, or check if it looks like a sentence.
    target = _join_rest(cleaned)
    tokens = _TOKEN_RE.findall(target)
    if len(tokens) > 1:
        return _print_check(check_text(target), as_json=json_out)
    return _print_lookup(lookup(target), as_json=json_out)


if __name__ == "__main__":
    raise SystemExit(main())
