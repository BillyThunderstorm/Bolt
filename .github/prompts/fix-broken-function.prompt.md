---
mode: ask
description: "Use when: a function in a file is broken, throwing an error, or producing incorrect behavior and you need a targeted fix."
---

# Fix a broken function

Investigate a broken function in the provided file and repair it with a minimal, reliable change.

## Inputs

- File: {{file}}
- Function or symbol: {{function}}
- Error, symptom, or expected behavior: {{issue}}
- Relevant selection or surrounding code: {{selection}}

## Instructions

1. Read the target file and surrounding context carefully.
2. Identify the root cause of the breakage rather than patching symptoms.
3. Explain the problem briefly in plain language.
4. Apply the smallest fix that resolves the issue and preserves existing behavior.
5. If possible, verify the result by reasoning through the flow or running a relevant test or repro.
6. Summarize the change, why it works, and any follow-up considerations.

## Output format

- Root cause
- Proposed fix
- What changed
- Verification notes
- Any remaining risks or follow-up steps
