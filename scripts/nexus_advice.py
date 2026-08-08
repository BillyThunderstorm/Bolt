#!/usr/bin/env python3
"""
Nexus CLI

By default uses free local Ollama only.
Add ``--paid`` to allow the xAI Grok API for this one call
(also enabled globally with NEXUS_ALLOW_PAID=true).
Gemini is not used unless NEXUS_USE_GEMINI=true.
"""

import sys
from pathlib import Path

# Ensure Core is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Core"))

from modules.Nexus_Creator import NexusCreator

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            'Usage: bolt nexus "your question" '
            "[--task-type TYPE] [--complexity high/medium] [--paid]"
        )
        sys.exit(1)

    topic = sys.argv[1]
    task_type = "general"
    complexity = "medium"
    allow_paid = "--paid" in sys.argv

    if "--task-type" in sys.argv:
        idx = sys.argv.index("--task-type") + 1
        if idx < len(sys.argv):
            task_type = sys.argv[idx]
    if "--complexity" in sys.argv:
        idx = sys.argv.index("--complexity") + 1
        if idx < len(sys.argv):
            complexity = sys.argv[idx]

    nexus = NexusCreator()
    result = nexus.consult(
        topic,
        task_type=task_type,
        complexity=complexity,
        allow_paid=allow_paid if allow_paid else None,
    )

    print("\n=== Nexus Advice ===\n")
    print(
        result["advice"]
        or "(no advice — start Ollama, or use --paid for Grok API)"
    )
    print(
        f"\nProvider: {result.get('provider', 'unknown')} | "
        f"Model: {result.get('model', 'unknown')}"
        + (" | paid allowed" if allow_paid else " | free path")
    )
