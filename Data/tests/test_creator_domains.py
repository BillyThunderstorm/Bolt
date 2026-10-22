"""Targeted tests for Creator_Domains (bolt domains). Temp files only."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
from modules import Creator_Domains as cd  # noqa: E402

REQ = """# Reqs

## 1. Content Creation
### Purpose
Make posts. See `Data/nope/missing.md`.

## 2. Live Streaming
### Purpose
Stream well.

---

## Cross-Domain Priorities
1. Live Streaming first.
"""

INS = """# Instr

## Domain Behaviors

### 1. Content Creation
One idea at a time.
```
## not a heading inside a fence
```

### 2. Live Streaming
Stay quiet. Watch for burnout.

## Burnout Detection Rules
Mention it cheerfully.
"""


@pytest.fixture
def docs(tmp_path, monkeypatch):
    r = tmp_path / "req.md"
    i = tmp_path / "ins.md"
    r.write_text(REQ)
    i.write_text(INS)
    monkeypatch.setattr(cd, "_REQUIREMENTS", r)
    monkeypatch.setattr(cd, "_INSTRUCTIONS", i)
    monkeypatch.setattr(cd, "_REPO", tmp_path)
    return r, i


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_status_ready_and_agree(docs):
    info = cd.status(probe=True)
    assert info["ready"] and info["docs_agree"] and info["probe_ok"]
    assert info["domain_count"] == 2
    assert any("Data/nope/missing.md" in s for s in info["stale_refs"])


def test_status_flags_mismatch(docs):
    _, i = docs
    i.write_text(INS.replace("### 2. Live Streaming", "### 2. Streaming Live"))
    info = cd.status(probe=True)
    assert info["ready"] and not info["docs_agree"] and not info["probe_ok"]
    assert "rename one" in info["mismatches"][0]


def test_status_missing_file_soft_fails(docs):
    r, _ = docs
    r.unlink()
    info = cd.status()
    assert not info["ready"]
    assert info["hint"].startswith("Domains unavailable:")


def test_show_domain_has_both_parts(docs, capsys):
    cd.show_domain("2", as_json=True)
    d = _json(capsys)
    assert d["ok"] and "Stream well" in d["requirements"]
    assert "Stay quiet" in d["behavior"]
    assert "Cross-Domain" not in d["requirements"]


def test_show_by_word_and_fence_ignored(docs, capsys):
    cd.show_domain("content", as_json=True)
    d = _json(capsys)
    assert d["domain"]["id"] == 1
    assert "not a heading inside a fence" in d["behavior"]


def test_show_other_section(docs, capsys):
    cd.show_domain("priorities", as_json=True)
    d = _json(capsys)
    assert d["ok"] and "Live Streaming first" in d["body"]
    cd.show_domain("burnout", as_json=True)
    assert "cheerfully" in _json(capsys)["body"]


def test_show_unknown_and_bad_number(docs, capsys):
    cd.show_domain("9", as_json=True)
    assert not _json(capsys)["ok"]
    cd.show_domain("xyzzy", as_json=True)
    assert "search" in _json(capsys)["error"]


def test_search(docs, capsys):
    cd.search("burnout", as_json=True)
    d = _json(capsys)
    assert d["count"] == 2
    assert {r["doc"] for r in d["results"]} == {"instructions"}


def test_open_print_only(docs, capsys):
    cd.open_doc("instructions", print_only=True, as_json=True)
    d = _json(capsys)
    assert d["ok"] and not d["opened"] and d["path"].endswith("ins.md")


def test_main_routes(docs, capsys):
    assert cd.main(["search", "quiet", "--json"]) == 0
    assert _json(capsys)["count"] == 1
    assert cd.main(["2", "--json"]) == 0
    assert _json(capsys)["domain"]["id"] == 2
