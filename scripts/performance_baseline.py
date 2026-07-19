#!/usr/bin/env python3
"""
Performance Baseline Script for Bolt
Measures startup time, memory usage, and response times.
Run this before and after optimizations to compare performance.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

# Configuration
RESULTS_DIR = Path("logs/performance")
RESULTS_FILE = RESULTS_DIR / f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def ensure_results_dir():
    """Create results directory if it doesn't exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    try:
        import psutil

        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        # Fallback using /proc on Linux or taskutil on macOS
        try:
            result = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) / 1024  # Convert KB to MB
        except Exception:
            pass
    return 0.0


def measure_startup_time(script: str) -> dict:
    """Measure how long a script takes to start (syntax check + import test)."""
    result = {
        "script": script,
        "syntax_check_sec": None,
        "import_test_sec": None,
        "error": None,
    }

    try:
        # Check syntax only (fast)
        start = time.time()
        with open(script, "r") as f:
            compile(f.read(), script, "exec")
        elapsed = time.time() - start
        result["syntax_check_sec"] = round(elapsed, 4)
    except SyntaxError as e:
        result["error"] = f"Syntax error: {e}"
    except Exception as e:
        result["error"] = str(e)

    return result


def measure_import_time(module: str) -> dict:
    """Measure how long a module takes to import."""
    result = {"module": module, "import_time_sec": None, "error": None}

    try:
        start = time.time()
        __import__(module)
        elapsed = time.time() - start
        result["import_time_sec"] = round(elapsed, 4)
    except Exception as e:
        result["error"] = str(e)

    return result


def check_system_resources() -> dict:
    """Check current system resource usage."""
    resources = {
        "cpu_count": os.cpu_count(),
        "memory_total_gb": 0,
        "memory_available_gb": 0,
        "disk_free_gb": 0,
    }

    try:
        import psutil

        resources["memory_total_gb"] = round(
            psutil.virtual_memory().total / 1024 / 1024 / 1024, 2
        )
        resources["memory_available_gb"] = round(
            psutil.virtual_memory().available / 1024 / 1024 / 1024, 2
        )
    except ImportError:
        pass

    # Disk free space
    try:
        stat = os.statvfs("/")
        resources["disk_free_gb"] = round(
            (stat.f_bavail * stat.f_frsize) / 1024 / 1024 / 1024, 2
        )
    except Exception:
        pass

    return resources


def run_baseline() -> dict:
    """Run full performance baseline."""
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    print("=" * 60)
    print("Bolt Performance Baseline")
    print("=" * 60)
    print()

    results = {
        "timestamp": datetime.now().isoformat(),
        "system": check_system_resources(),
        "module_imports": [],
        "script_startup": [],
        "notes": [],
    }

    # Core modules to test
    core_modules = [
        "modules.Config_Loader",
        "modules.Bolt_Memory",
        "modules.Bolt_Chat",
        "modules.Bolt_Voice",
        "modules.Clip_Generator",
        "modules.Highlight_Detector",
        "modules.Memory_Index",
        "modules.Think_Learn_Decide",
    ]

    print("Testing module import times...")
    for module in core_modules:
        print(f"  Importing {module}...", end=" ")
        result = measure_import_time(module)
        results["module_imports"].append(result)
        if result["error"]:
            print(f"ERROR: {result['error']}")
        else:
            print(f"{result['import_time_sec']:.4f}s")

    # Scripts to test
    scripts = [
        "launch.py",
        "bot.py",
    ]

    print()
    print("Testing script startup times...")
    for script in scripts:
        if Path(script).exists():
            print(f"  Checking {script}...", end=" ")
            result = measure_startup_time(script)
            results["script_startup"].append(result)
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                print(f"{result['syntax_check_sec']:.4f}s")
        else:
            print(f"  Skipping {script} (not found)")

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_import_time = sum(
        r.get("import_time_sec", 0) or 0 for r in results["module_imports"]
    )
    print(f"Total module import time: {total_import_time:.3f}s")

    if results["script_startup"]:
        valid_syntax = [
            r
            for r in results["script_startup"]
            if r.get("syntax_check_sec") is not None
        ]
        if valid_syntax:
            avg_syntax = sum(r["syntax_check_sec"] for r in valid_syntax) / len(
                valid_syntax
            )
            print(f"Average script syntax check: {avg_syntax:.4f}s")

    print(
        f"System memory: {results['system']['memory_total_gb']}GB total, {results['system']['memory_available_gb']}GB available"
    )
    print(f"Disk free: {results['system']['disk_free_gb']}GB")

    # Save results
    ensure_results_dir()
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print()
    print(f"Results saved to: {RESULTS_FILE}")

    return results


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Usage: python3 scripts/performance_baseline.py")
        print()
        print("Measures startup time, memory usage, and response times.")
        print("Results are saved to logs/performance/ for comparison.")
        sys.exit(0)

    run_baseline()
