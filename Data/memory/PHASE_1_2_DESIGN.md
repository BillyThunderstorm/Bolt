# Phase 1.2 — Memory Consolidation

**Status:** ✅ Complete (2026-07-31, evening session).
**Outcome:** 33→4 broken tests in the Bolt suite. The remaining 4 are
pre-existing PIL/loader issues in `test_video_intelligence` and
`test_highlight_series` / `test_video_to_title_integration` — unrelated to
this phase.
**Author:** Carter + Agent (test-driven delivery).

> This doc was originally authored as a high-level design plan by an earlier
> Codex / Bolt-agent session in the morning of 2026-07-31. It got the spirit
> right but the contracts wrong: it described `_retrieve_briefing_memory`
> without specifying the prefixes / headings / model types the on-disk tests
> actually assert on. The evening session treated the **on-disk tests as the
> source of truth** rather than the plan, and shipped accordingly. The lower
> section ("What was actually built") is the post-shipment record.

---

## Problem statement (revised)

Three of the briefing / decision modules had a memory-awareness contract
that did not match what the test suite assumed. The mismatch was deeper
than the original doc recognized — not just a missing function, but a
missing API on three call sites:

- `scripts/weekly_analysis.py` — the report used "## Recommendations" and
  prefix "Follow up on recent decision:" / "Creator note active:". The tests
  expect the report to use "## Recommendations for Next Week" with three
  different prefixes by hit kind, and to gate a 🧠 "Memory Highlights"
  section. Module was missing `send_sms` / `send_email` / `load_outcomes` /
  `load_queue_stats`.
- `Core/modules/Think_Learn_Decide.py` — was missing `propose_actions()`
  entirely. `think_and_propose()` returned plain dicts, not `ProposedAction`,
  and never applied the memory deltas to candidate confidences. Reasons did
  not include the strongest-match title; no way to keep caller-provided
  `memory_influence` from being overwritten.
- `scripts/daily_briefing.py` — already had memory-grounded action items
  from an earlier session; tests passed with no changes.

This blocked:
- Memory-grounded daily briefings (already shipped)
- Memory-grounded weekly analysis (shipped 2026-07-31 evening)
- Confidence deltas on `ProposedAction` from retrieved memory
  (shipped 2026-07-31 evening)

## Audit findings (revised — what was actually on disk before this phase)

### Test count status

| Scope | Before | After (this phase) |
|---|---|---|
| `test_daily_briefing.py` | 11/11 ✅ | 11/11 ✅ (untouched) |
| `test_weekly_analysis.py` | 0/8 ❌ | 8/8 ✅ |
| `test_think_learn_decide.py` | 3/15 ❌ | 15/15 ✅ |
| Whole `Data/tests/` suite | 33 broken | **4 broken** (all pre-existing PIL/loader errors, verified via `git stash` baseline) |

> The original doc claimed "29 pre-existing test errors." The actual
> starting count — measured after the morning of 2026-07-31 — was **33**.
> Both numbers are consistent with the design doc framing, but the precise
> figure matters because the goal of this phase was the *29 in-memory-
> consolidation* errors, not the 4 orthogonal PIL/loader ones.

### Files in scope (this phase)

- `scripts/weekly_analysis.py` — fully rewritten at the report layer.
- `Core/modules/Think_Learn_Decide.py` — added `propose_actions()`, cleaned
  `think_and_propose()`, removed dead code at the end of the old method.
- `scripts/daily_briefing.py` — no changes (already conformed).
- `Core/modules/Bolt_Memory.py` — no changes. `_retrieve_briefing_memory`
  exists in both `daily_briefing.py` and `weekly_analysis.py`, which is
  where the test suite patches it. There was no need to add a copy on
  `Bolt_Memory`.

---

## What `weekly_analysis` actually renders now

Report shape (rendered by `generate_insights`):

```
# Bolt Weekly Analysis
**Week ending <date>**

## Performance Summary
- Clips logged this week: N
- Total queue items: N
- Memory hits: N
---

## 🧠 Memory Highlights
- [<kind>] <title or text> (source: <source>)
... (one line per memory hit)
---

## Recommendations for Next Week
1. <Honor creator note / Carry forward recent decision / Reflect last week's outcome / generic>
... (capped: 1-3 hits → all, 4+ hits → cap=2)
---
```

Recommendations prefix mapping (the test source of truth):

| Hit kind | Prefix |
|---|---|
| `markdown` / `creator_note` | `Honor creator note: <title or text>` |
| `decision_event` | `Carry forward recent decision: <action>` |
| `performance_outcome` | `Reflect last week's outcome: <title>` |
| other | raw title or text (no prefix) |

Dedup rule: highest-scoring hit wins per theme prefix (the part before
the first `:` in the rec). Capping rule: dual (≤3 hits → all surface,
>3 → cap=2). This dual rule is the explicit reason the original code
failed `test_recommendations_capped_and_deduped` — it capped at 5 always.

When memory hits are empty, the fallback is `1. Start logging performance`
(matches `test_report_falls_back_when_no_memory`). No more
"Review performance and adjust content mix".

CLI:

```
python scripts/weekly_analysis.py [--print] [--send] [--days N]
```

`--send` calls `send_sms(...)` and `send_email(...)` (both module-level,
both no-op by default, both patchable by tests).

## What `Think_Learn_Decide` actually exposes now

### New: `propose_actions(candidates) -> List[ProposedAction]`

```python
proposal = ProposedAction(
    action_id=f"{action}:{clip_path}:{index}",
    action=action,
    confidence=score / 100  # clamped 0..1, base
    risk="high" if action in {delete_clip, publish_now} else "low"
    reason="score N → confidence 0.NN; memory boosted confidence by 0.04 — strongest match: <title>"
    payload={"clip_path": ..., "score": ..., ...}
)
```

Each candidate is at minimum `{action, score, clip_path}` and may
optionally carry:

- `memory_context: List[dict]` — memory hits to fold into the decision
- `memory_influence: dict` — pre-computed influence override
  (caller wins when present)
- `retrieved_memory: List[dict]` — alias for `memory_context`

Confidence pipeline per candidate:

1. `base = score / 100` (clamped to `[0, 1]`)
2. `adjustment, reason = candidate.memory_influence.confidence_delta`
   if `memory_influence` is present, else derive from `memory_context`
   via `_memory_adjustment()` (signal + keyword heuristics)
3. `confidence = clamp(0..1, base + adjustment)`
4. `reason = "<base>; memory boosted/reduced confidence by <Δ> — strongest match: <title>"`
   when `|adjustment| ≥ 0.005`, otherwise plain base reason.

Sorted by `confidence` descending. Ties broken by input order (stable).

### Revised: `think_and_propose(input, candidates)`

Now delegates to `propose_actions` instead of attaching raw `memory_influence`
to candidates and returning raw dicts. Caller-supplied `memory_influence` is
still preserved (`test_caller_provided_memory_influence_is_not_overwritten`).
Added the `timestamp` and `nexus_insight` keys to the thought dict (already
in the original).

## Success criteria (revised — what got verified)

1. ✅ All 33 currently-broken tests pass *except* the 4 orthogonal PIL/loader
   errors that were broken before this phase started (verified by running
   `git stash` and re-running the suite at session start).
2. ✅ `weekly_analysis._retrieve_weekly_memory` and `_memory_to_recommendations`
   are patchable per the test fixtures.
3. ✅ When memory retrieval returns `[]`, both briefings still render with
   generic fallback content.
4. ✅ When memory hits are available, they surface in the briefing with the
   correct prefixes (markdown → "Honor creator note:", decision_event →
   "Carry forward recent decision:", performance_outcome → "Reflect last
   week's outcome").
5. ✅ `Think_Learn_DecideEngine.propose_actions()` returns `ProposedAction`
   objects whose `.confidence` shifts up/down with memory signals and whose
   `.reason` references the strongest-match title.
6. ✅ No new tests were broken: full suite went from 33 errors → 4 errors,
   with each of the 4 surviving errors confirmed pre-existing on `main`.

## What we explicitly did NOT do (matches the original non-goals)

- ❌ **`Local_Vector_DB.py` activation** — still deferred. The
  `memory_index.json` already provides vector-style retrieval via
  `Memory_Index.py`.
- ❌ **Migrating or replacing existing memory files** —
  `Data/memory_index.json` and `Data/unified_memory.jsonl` are still in
  use. `Data/memory/` (the user-facing folder) coexists with them.
- ❌ **Docs / README updates** — out of scope.

## What we did beyond the original doc

- Added `load_outcomes(days)` and `load_queue_stats()` to
  `weekly_analysis.py` (the `--send` flow uses them).
- Added `send_sms(text)` and `send_email(text)` as module-level helpers
  (patchable in tests). Wired to `Bolt_Alerts` on 2026-08-20 so
  `bolt weekly --send` uses the same SMS/email path as `bolt send`.
- Added a `risk` field on every `ProposedAction` ("high" for
  `delete_clip` / `publish_now`; "low" otherwise) so
  `enforce_action_policy` and `confirm_action` correctly gate
  high-risk actions — this implicitly makes the test
  `test_proposal_ranking_and_policy` pass.
- Removed dead code at the end of the old `think_and_propose()`.

## Effort (recorded for context)

Single evening session. Roughly:

- 10 min: reading the design doc + the three test files + the existing
  impl of each.
- 5 min: confirming with the user (test-as-spec vs doc-as-spec).
- 20 min: rewriting `weekly_analysis.py`.
- 25 min: wiring `propose_actions()` + cleaning `think_and_propose()`.
- 5 min: running tests + iterating to green.
- 5 min: full-suite baseline (`git stash`).
- 5 min: writing this doc.

**Total: ~75 min.** The original doc's 1–2 session estimate tracked well;
the main difference was *what* shipped (test-driven contract vs the doc's
informal spec), not how long.

---

## Appendix A — Test fixtures that drove the interface

The on-disk tests in `Data/tests/test_weekly_analysis.py` and
`Data/tests/test_think_learn_decide.py` are the source of truth for the
contracts this phase implemented. Where the design doc was vague
("memory hits ranked by score, capped at 3–5"), the tests pinned the
exact behavior (dual-cap at ≤3 and >3; theme-prefix dedup; specific
recommendation prefixes; emoji-prefixed heading; deterministic
`action_id` shape).

If you change any of the prefixes / headings / cap / dedup rules in
this implementation, expect the relevant test to fail and update the
test alongside the implementation in the same commit.

## Appendix B — Pre-existing 4 errors (out of Phase 1.2 scope)

These were broken before this phase and remain so:

- `test_video_intelligence.BlackFrameDetectionTests.test_solid_black_is_black`
  → `ModuleNotFoundError: No module named 'PIL'`
- `test_video_intelligence.BlackFrameDetectionTests.test_solid_white_is_not_black`
  → same
- `test_highlight_series` (loader error) → `NameError: name 'Image' is not
  defined` in `Core/modules/Clip_Deduplicator.py`
- `test_video_to_title_integration` (loader error) → same as above

Fixing these belongs in a separate phase (e.g., "Phase 1.3 — fix video
processing tests"): install Pillow, restore lazy `Image` import in
Clip_Deduplicator, and confirm the highlight / title-integration tests
load and pass.
