# Think/Learn/Decide Schema

Bolt stores normalized memory events in `data/unified_memory.jsonl`.

Each line follows this canonical schema:

```json
{
  "timestamp": "2026-04-28T18:30:00.000000",
  "source": "clip_history",
  "intent": "structured_state",
  "action": "ingest_json",
  "result": "loaded",
  "confidence": 0.85,
  "reason": "Ingested JSON state from clip_history.json",
  "feedback": "accepted|rejected|null",
  "metadata": {}
}
```

## Decision Safety

- `decision_allowlist`: actions Bolt is allowed to execute.
- `decision_denylist`: actions always blocked.
- `logs/decision_audit.log`: append-only audit trail for think/proposal/confirmation/execution.

## Learning Stores

- `data/decision_model.json`
  - `weights`: scoring weight mix.
  - `feedback_by_action`: cumulative user preference per action.
  - `outcomes_by_action`: success/total counters used for confidence calibration.

