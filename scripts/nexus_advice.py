#!/usr/bin/env python3
"""
Nexus CLI
"""

import sys
import os
from pathlib import Path

# Ensure Core is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Core"))

from modules.Nexus_Creator import NexusCreator

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: bolt nexus \"your question\" [--task-type TYPE] [--complexity high/medium]")
        sys.exit(1)

    topic = sys.argv[1]
    task_type = "general"
    complexity = "medium"

    if "--task-type" in sys.argv:
        idx = sys.argv.index("--task-type") + 1
        if idx < len(sys.argv):
            task_type = sys.argv[idx]
    if "--complexity" in sys.argv:
        idx = sys.argv.index("--complexity") + 1
        if idx < len(sys.argv):
            complexity = sys.argv[idx]

    nexus = NexusCreator()
    result = nexus.consult(topic, task_type=task_type, complexity=complexity)
    
    print("\n=== Nexus Advice ===\n")
    print(result["advice"])
    print(f"\nProvider: {result.get('provider', 'unknown')} | Model: {result.get('model', 'unknown')}")