# Phase 1.x Verification Checklist

**Date shipped:** 2026-07-31 (Phases 1.2, 1.3, 1.4)
**Branch:** `origin/main` @ commit `5896e391` (Phase 1.4 cleanup)
**Test result:** 310 passed, 5 skipped, 0 broken (via three entry points)

> **Print this page.** It is the only verification you need to run after
> pulling Phase 1.x to confirm the work landed cleanly on your box.

---

## Three things to do after testing the fix

### 1. Confirm you can run the suite two ways (uv + raw venv)

```bash
cd /Users/carter/developer/Bolt

uv --version                                            # expect 0.10+
uv run --directory /Users/carter/developer/Bolt python \
    -m unittest discover Data/tests 2>&1 | tail -3
                                                       # expect: Ran 310 tests … OK (skipped=5)

.venv/bin/python -m unittest discover Data/tests 2>&1 | tail -3
                                                       # expect: Ran 310 tests … OK (skipped=5)
```

> Why both: `uv run` is the canonical (uses uv.lock + pinned Python);
> `.venv/bin/python` is the raw venv (proves the venv itself has every
> dep installed correctly without going through `uv`). If ONLY `uv run`
> works but `.venv/bin/python` fails, you need `uv sync --refresh` to
> rebuild the venv against the current lockfile.

If `uv run` fails with `No module named 'PIL'` you haven't run
`uv sync` yet — do:

```bash
uv sync               # one-time, populates .venv from uv.lock
```

> **Note:** plain `python -m unittest discover` (using the system Python
> at `/usr/local/bin/python3`) will fail on the `BlackFrameDetectionTests`
> because Pillow is no longer globally installed after the Phase 1.4
> cleanup. That's expected. Use `uv run` or `.venv/bin/python` to get
> the full set.

### 2. Smoke-test the new memory-aware briefings (Phase 1.2 contract)

```bash
cd /Users/carter/developer/Bolt

uv run --directory /Users/carter/developer/Bolt bolt briefing --print 2>&1 | head -25
```

What you should see in the rendered markdown:

- A **`## Memory Notes`** section listing every retrieved hit.
- A **`## Action Items For Today`** section that **starts** with
  `Review last clip performance and log outcomes` when memory has
  performance outcomes, otherwise `Review clip performance and log
  results` (the generic fallback).
- An SMS summary line that ends with `N memory notes`.

Then:

```bash
uv run --directory /Users/carter/developer/Bolt bolt weekly --print 2>&1 | head -30
```

What you should see:

- A **`## 🧠 Memory Highlights`** section (note the brain emoji prefix).
- A **`## Recommendations for Next Week`** section (renamed from
  `## Recommendations` in Phase 1.2).
- Recommendation lines with one of these prefixes by hit kind:
  - `Honor creator note: <title>` — for `markdown` / `creator_note` hits
  - `Carry forward recent decision: <action>` — for `decision_event` hits
  - `Reflect last week's outcome: <title>` — for `performance_outcome` hits
  - `Start logging performance` — the fallback (when memory returns [])

### 3. Smoke-test the new `propose_actions()` decision path (Phase 1.2 contract)

```bash
cd /Users/carter/developer/Bolt
uv run --directory /Users/carter/developer/Bolt python <<'PY'
from modules.Think_Learn_Decide import ThinkLearnDecideEngine

engine = ThinkLearnDecideEngine({})
candidates = [
    {"action": "queue_clip", "score": 82, "clip_path": "media/clips/ace.mp4"},
    {"action": "delete_clip", "score": 95, "clip_path": "media/clips/old.mp4"},
    {"action": "queue_clip", "score": 70, "clip_path": "media/clips/kill.mp4"},
]
proposals = engine.propose_actions(candidates)

for p in proposals:
    print(f"  {p.action:12s} conf={p.confidence:.2f}  risk={p.risk:5s}  reason={p.reason}")
PY
```

What you should see (order may vary, but `delete_clip` MUST come first
because score 95 > 82):

```
  delete_clip  conf=0.95  risk=high  reason=score 95 → confidence 0.95
  queue_clip   conf=0.82  risk=low   reason=score 82 → confidence 0.82
  queue_clip   conf=0.70  risk=low   reason=score 70 → confidence 0.70
```

Two sanity checks to do with your eyes:

- **`delete_clip` appears first** (highest score wins), AND it has
  `risk=high` in front of it — `enforce_action_policy()` would refuse to
  execute it even though it won the rank.
- The `queue_clip` lines do NOT mention "memory" yet (no retrieval
  happened). That's expected — memory-aware reranking only activates when
  either `think()` ran first (via `think_and_propose`) OR you passed
  `memory_influence` on a candidate dict.

---

## New canonical commands (cheat-sheet)

| Purpose | Command |
|---|---|
| **Run the test suite** | `uv run --directory /Users/carter/developer/Bolt bolt test` |
| **Print daily briefing** | `uv run --directory /Users/carter/developer/Bolt bolt briefing --print` |
| **Send daily briefing** | `uv run --directory /Users/carter/developer/Bolt bolt briefing --send` |
| **Print weekly analysis** | `uv run --directory /Users/carter/developer/Bolt bolt weekly --print` |
| **Last-N-days window** | `uv run --directory /Users/carter/developer/Bolt bolt weekly --days 14` |
| **Refresh memory index** | `uv run --directory /Users/carter/developer/Bolt bolt refresh_memory` |
| **Ask Nexus for advice** | `uv run --directory /Users/carter/developer/Bolt bolt nexus "How do I title my Marvel Rivals clips?"` |
| **Run an ad-hoc Python script** | `uv run --directory /Users/carter/developer/Bolt python script.py` |
| **Verify install** | `uv run --directory /Users/carter/developer/Bolt bolt verify` |
| **Set up shell alias (one-time)** | add to `~/.zshrc`: `alias bolt='uv run --directory /Users/carter/developer/Bolt bolt'` then `source ~/.zshrc` |

---

## What changed in each phase (so you can review at a glance)

| Phase | Files touched | What it does |
|---|---|---|
| **1.2 — Memory consolidation** | `scripts/weekly_analysis.py` (rewrite), `Core/modules/Think_Learn_Decide.py` (added `propose_actions()`, cleaned `think_and_propose()`) | Briefings and decisions now use memory hits with kind-specific prefixes; `propose_actions()` returns `ProposedAction` objects with confidence/reason |
| **1.3 — Video processing test repairs** | `Core/modules/Clip_Deduplicator.py` (added `from __future__ import annotations`) | Module imports cleanly even when Pillow is missing |
| **1.4 — Full uv migration** | `pyproject.toml`, `uv.lock`, `.python-version` (new), `scripts/activate_bolt_venv.sh` (prefers `uv run`), `bin/bolt` (docstring updated) | Bolt is reproducible: `uv sync` from a fresh clone produces the same `.venv` every time |

The design doc for each phase lives in `Data/memory/PHASE_1_*_DESIGN.md`:
`PHASE_1_2_DESIGN.md`, `PHASE_1_3_DESIGN.md`, `PHASE_1_4_DESIGN.md`.

---

## If any step fails — what to check first

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv: command not found` | uv isn't installed on this box | Install from https://docs.astral.sh/uv/, then `cd Bolt && uv sync` |
| `No module named 'PIL'` after `uv sync` | Lockfile drift — venv wasn't rebuilt | `uv sync --refresh` then re-run the suite |
| Briefing prints but no Memory Notes section | Memory stack failed silently (returned []) | Run `bolt refresh_memory` then re-run briefing; check `Data/data/memory_index.json` exists |
| Weekly report missing the 🧠 emoji block | Weekly analysis ran with 0 memory hits — that's a real "no memory yet" state, not a bug | Log a clip performance with `bolt log_perf` and try again |
| `delete_clip` did NOT come first in step 3 | Python script typo on `score` keys | Re-check the candidate dict; `score` must be a number, not a string |
| Any test fails | A new test was added without updating source OR local files were edited | Run `git status`; revert any local changes to Core/scripts; re-run `uv sync` if the lockfile moved |

If after those you're still stuck: open the relevant `PHASE_1_x_DESIGN.md`
under `Data/memory/` — each one has a "What was actually built" section
with the verified test counts and the specific contract that was locked in.

---

*This page is meant to be one printed sheet. Don't print the
1269-line `Core/modules/BOLT_COMMANDS.md` — it has the full history.
Print this file instead.*
