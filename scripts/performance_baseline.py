#!/usr/bin/env python3
"""
performance_baseline.py — Bolt speed check (engine for `bolt performance run`)
=============================================================================
Times how long Bolt takes to start, measured the honest way: every item runs
in a FRESH Python process (cold import, like a real launch), repeated a few
times, and the median is kept. Then compares against the previous saved
baseline and prints a plain report.

  python3 scripts/performance_baseline.py [--quick] [--repeats N]
                                          [--json] [--no-save]

Saves logs/performance/baseline_YYYYMMDD_HHMMSS.json (method "fresh-process-v2").
Local only: no network, no keys, nothing spoken, nothing deleted.
Optional: psutil (memory numbers). Missing third-party libraries are listed
as "not installed (optional)", never an error.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT  # noqa: E402

PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT
CORE_DIR = REPO_ROOT / "Core"
RESULTS_DIR = REPO_ROOT / "logs" / "performance"
METHOD = "fresh-process-v2"
DEFAULT_REPEATS = 3
ITEM_TIMEOUT = 60

# Bolt's own modules (cold import each)
CORE_MODULES = [
    "modules.Config_Loader",
    "modules.notifier",
    "modules.LLM_Handler",
    "modules.Bolt_Memory",
    "modules.Bolt_Chat",
    "modules.Bolt_Voice",
    "modules.Clip_Generator",
    "modules.Clip_Ranker",
    "modules.Highlight_Detector",
    "modules.Memory_Index",
    "modules.Think_Learn_Decide",
]
# Big third-party libraries the clip pipeline may pull in
LIBRARIES = ["numpy", "scipy", "cv2", "librosa", "torch", "openai", "requests"]
SCRIPTS = ["Core/launch.py", "Core/bot.py"]

# A change only counts when it is BOTH this much slower in seconds and by %.
SLOWER_SEC = 0.05
SLOWER_PCT = 25.0


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _env() -> Dict[str, str]:
    env = os.environ.copy()
    extra = f"{CORE_DIR}:{_SCRIPT_DIR}"
    env["PYTHONPATH"] = extra + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _time_snippet(code: str, repeats: int, py: str) -> Dict[str, Any]:
    """Run `code` in fresh processes; it must print elapsed seconds last."""
    times: List[float] = []
    err = ""
    for _ in range(max(1, repeats)):
        try:
            proc = subprocess.run(
                [py, "-c", code], cwd=str(REPO_ROOT), env=_env(),
                capture_output=True, text=True, timeout=ITEM_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            err = f"timed out after {ITEM_TIMEOUT}s"
            break
        if proc.returncode != 0:
            lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            err = lines[-1] if lines else f"exit {proc.returncode}"
            break
        try:
            times.append(float((proc.stdout or "").strip().splitlines()[-1]))
        except Exception:
            err = "could not read timing"
            break
    out: Dict[str, Any] = {"seconds": None, "runs": [round(t, 4) for t in times], "error": err or None}
    if times and not err:
        out["seconds"] = round(statistics.median(times), 4)
    return out


def _time_command(argv: List[str], repeats: int) -> Dict[str, Any]:
    """Wall-clock a whole command (process start → exit)."""
    times: List[float] = []
    err = ""
    for _ in range(max(1, repeats)):
        t = time.perf_counter()
        try:
            proc = subprocess.run(argv, cwd=str(REPO_ROOT), env=_env(),
                                  capture_output=True, text=True, timeout=ITEM_TIMEOUT)
        except subprocess.TimeoutExpired:
            err = f"timed out after {ITEM_TIMEOUT}s"
            break
        except Exception as exc:
            err = str(exc)
            break
        el = time.perf_counter() - t
        if proc.returncode != 0:
            lines = (proc.stderr or "").strip().splitlines()
            err = lines[-1] if lines else f"exit {proc.returncode}"
            break
        times.append(el)
    out: Dict[str, Any] = {"seconds": None, "runs": [round(t, 4) for t in times], "error": err or None}
    if times and not err:
        out["seconds"] = round(statistics.median(times), 4)
    return out


def _import_code(mod: str) -> str:
    return ("import time;t=time.perf_counter();import " + mod +
            ";print(time.perf_counter()-t)")


def measure_startup_time(script: str) -> dict:
    """Syntax-compile a script (kept for backward compatibility)."""
    result = {"script": script, "syntax_check_sec": None, "error": None}
    try:
        start = time.perf_counter()
        with open(script, "r", encoding="utf-8") as f:
            compile(f.read(), script, "exec")
        result["syntax_check_sec"] = round(time.perf_counter() - start, 4)
    except SyntaxError as e:
        result["error"] = f"Syntax error: {e}"
    except Exception as e:
        result["error"] = str(e)
    return result


def check_system_resources() -> dict:
    res: Dict[str, Any] = {
        "cpu_count": os.cpu_count(),
        "memory_total_gb": None,
        "memory_available_gb": None,
        "disk_free_gb": None,
        "load_avg_1m": None,
        "python": platform.python_version(),
        "macos": platform.mac_ver()[0] or None,
        "psutil": False,
    }
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        res["memory_total_gb"] = round(vm.total / 1024 ** 3, 2)
        res["memory_available_gb"] = round(vm.available / 1024 ** 3, 2)
        res["psutil"] = True
    except Exception:
        pass
    try:
        st = os.statvfs(str(REPO_ROOT))
        res["disk_free_gb"] = round(st.f_bavail * st.f_frsize / 1024 ** 3, 2)
    except Exception:
        pass
    try:
        res["load_avg_1m"] = round(os.getloadavg()[0], 2)
    except Exception:
        pass
    return res


def _git_commit() -> Optional[str]:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT),
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() or None
    except Exception:
        return None


def previous_baseline(exclude: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not RESULTS_DIR.is_dir():
        return None
    files = sorted(RESULTS_DIR.glob("baseline_*.json"), key=lambda p: p.name, reverse=True)
    for p in files:
        if exclude is not None and p.resolve() == exclude.resolve():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_path"] = str(p)
            return data
        except Exception:
            continue
    return None


def _flat_timings(data: Dict[str, Any]) -> Dict[str, float]:
    """name -> seconds for every timed item in a v2 baseline."""
    out: Dict[str, float] = {}
    for item in data.get("items") or []:
        if item.get("seconds") is not None:
            out[item["name"]] = float(item["seconds"])
    return out


def compare(current: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cmp: Dict[str, Any] = {"previous": None, "comparable": False, "slower": [], "faster": [],
                           "new": [], "note": ""}
    if not prev:
        cmp["note"] = "No earlier baseline — this run becomes the one to compare against."
        return cmp
    cmp["previous"] = prev.get("_path")
    cmp["previous_time"] = prev.get("timestamp")
    ps, cs = prev.get("system") or {}, current.get("system") or {}
    if ps.get("disk_free_gb") is not None and cs.get("disk_free_gb") is not None:
        cmp["disk_free_change_gb"] = round(cs["disk_free_gb"] - ps["disk_free_gb"], 2)
    if prev.get("method") != METHOD:
        cmp["note"] = ("Earlier baseline used the old in-process method (not comparable); "
                       "timing comparison starts with the next run.")
        return cmp
    cmp["comparable"] = True
    old, new = _flat_timings(prev), _flat_timings(current)
    for name, sec in new.items():
        if name not in old:
            cmp["new"].append(name)
            continue
        o = old[name]
        delta = sec - o
        pct = (delta / o * 100.0) if o > 0 else (100.0 if delta > 0 else 0.0)
        row = {"name": name, "before": o, "now": sec, "delta_sec": round(delta, 4),
               "delta_pct": round(pct, 1)}
        if delta >= SLOWER_SEC and pct >= SLOWER_PCT:
            cmp["slower"].append(row)
        elif -delta >= SLOWER_SEC and -pct >= SLOWER_PCT:
            cmp["faster"].append(row)
    cmp["total_before"] = prev.get("summary", {}).get("bolt_startup_sec")
    cmp["total_now"] = current.get("summary", {}).get("bolt_startup_sec")
    if not cmp["slower"]:
        cmp["note"] = "Nothing got noticeably slower since the last baseline."
    else:
        cmp["note"] = f"{len(cmp['slower'])} item(s) got noticeably slower since the last baseline."
    return cmp


def _fmt(sec: Optional[float]) -> str:
    if sec is None:
        return "—"
    return f"{sec * 1000:.0f} ms" if sec < 1 else f"{sec:.2f} s"


def build_report(r: Dict[str, Any]) -> str:
    s, sysr, c = r["summary"], r["system"], r["comparison"]
    L: List[str] = []
    L.append(f"Bolt speed check — {r['timestamp'][:16].replace('T', ' ')} (local time)")
    L.append("")
    L.append(f"  Verdict: {s['verdict']}")
    L.append(f"  Bolt startup (bot.py cold import): {_fmt(s.get('bolt_startup_sec'))}")
    L.append(f"  `bolt` command startup:            {_fmt(s.get('bolt_cli_sec'))}")
    L.append(f"  Bare Python startup:               {_fmt(s.get('python_startup_sec'))}")
    L.append("")
    L.append(f"  Slowest Bolt modules ({r['repeats']} fresh runs each, median):")
    for it in s.get("slowest_modules", []):
        L.append(f"    {it['name']:<34} {_fmt(it['seconds'])}")
    libs = [i for i in r["items"] if i["kind"] == "library"]
    if libs:
        L.append("  Big libraries (only loaded when a feature needs them):")
        for it in libs:
            val = _fmt(it["seconds"]) if it["seconds"] is not None else (
                "not installed (optional)" if it.get("missing") else f"error: {it['error']}")
            L.append(f"    {it['name']:<34} {val}")
    errs = [i for i in r["items"] if i["error"] and not i.get("missing")]
    if errs:
        L.append("  Problems:")
        for it in errs:
            L.append(f"    ✗ {it['name']}: {it['error']}")
    L.append("")
    L.append("  Compared with last baseline:")
    L.append(f"    {c['note']}")
    for row in c.get("slower", []):
        L.append(f"    slower: {row['name']} {_fmt(row['before'])} → {_fmt(row['now'])} (+{row['delta_pct']}%)")
    for row in c.get("faster", []):
        L.append(f"    faster: {row['name']} {_fmt(row['before'])} → {_fmt(row['now'])} ({row['delta_pct']}%)")
    if c.get("disk_free_change_gb") is not None:
        L.append(f"    disk free: {sysr.get('disk_free_gb')} GB ({c['disk_free_change_gb']:+} GB)")
    L.append("")
    mem = (f"{sysr['memory_available_gb']} of {sysr['memory_total_gb']} GB free"
           if sysr.get("memory_total_gb") else "memory: install psutil for numbers (optional: uv pip install psutil)")
    L.append(f"  Mac: {sysr.get('cpu_count')} cores · {mem} · disk free {sysr.get('disk_free_gb')} GB · "
             f"load {sysr.get('load_avg_1m')} · Python {sysr.get('python')}")
    if sysr.get("load_avg_1m") and sysr.get("cpu_count") and sysr["load_avg_1m"] > sysr["cpu_count"]:
        L.append("  Note: the Mac was busy during this check, so times may read high.")
    return "\n".join(L)


def run_baseline(repeats: int = DEFAULT_REPEATS, save: bool = True, quiet: bool = False) -> dict:
    os.chdir(REPO_ROOT)
    py = _python()
    started = time.perf_counter()
    stamp = datetime.now()
    results_file = RESULTS_DIR / f"baseline_{stamp.strftime('%Y%m%d_%H%M%S')}.json"

    def say(msg: str, end: str = "\n") -> None:
        if not quiet:
            print(msg, end=end, flush=True)

    say(f"Bolt speed check — timing in fresh processes ({repeats} runs each)…")
    items: List[Dict[str, Any]] = []

    def add(name: str, kind: str, res: Dict[str, Any], **extra: Any) -> None:
        row = {"name": name, "kind": kind, **res, **extra}
        items.append(row)
        if row.get("missing"):
            say(f"  {name:<34} not installed (optional)")
        elif row["error"]:
            say(f"  {name:<34} ERROR: {row['error']}")
        else:
            say(f"  {name:<34} {_fmt(row['seconds'])}")

    add("python startup", "startup", _time_command([py, "-c", "pass"], repeats))
    add("bolt help (CLI startup)", "startup", _time_command([py, str(REPO_ROOT / "bin" / "bolt"), "help"], repeats))
    add("bot.py import (Bolt startup)", "startup", _time_snippet(_import_code("bot"), repeats, py))
    for mod in CORE_MODULES:
        if not (CORE_DIR / (mod.replace(".", "/") + ".py")).exists():
            add(mod, "module", {"seconds": None, "runs": [], "error": None}, missing=True)
            continue
        add(mod, "module", _time_snippet(_import_code(mod), repeats, py))
    for lib in LIBRARIES:
        res = _time_snippet(_import_code(lib), repeats, py)
        missing = bool(res["error"] and ("No module named" in res["error"]))
        if missing:
            res["error"] = None
        add(lib, "library", res, missing=missing)

    scripts = []
    for sc in SCRIPTS:
        p = REPO_ROOT / sc
        if p.exists():
            scripts.append(measure_startup_time(str(p)))
        else:
            scripts.append({"script": sc, "syntax_check_sec": None, "error": "missing"})

    mods = [i for i in items if i["kind"] == "module" and i["seconds"] is not None]
    slowest = sorted(mods, key=lambda i: i["seconds"], reverse=True)[:5]
    by = {i["name"]: i for i in items}
    errors = [i for i in items if i["error"] and not i.get("missing")] + \
             [{"name": s["script"], "error": s["error"]} for s in scripts if s.get("error")]

    result: Dict[str, Any] = {
        "timestamp": stamp.isoformat(timespec="seconds"),
        "method": METHOD,
        "repeats": repeats,
        "python_executable": py,
        "git_commit": _git_commit(),
        "system": check_system_resources(),
        "items": items,
        "script_syntax": scripts,
        "summary": {
            "python_startup_sec": by["python startup"]["seconds"],
            "bolt_cli_sec": by["bolt help (CLI startup)"]["seconds"],
            "bolt_startup_sec": by["bot.py import (Bolt startup)"]["seconds"],
            "modules_total_sec": round(sum(i["seconds"] for i in mods), 4),
            "slowest_modules": [{"name": i["name"], "seconds": i["seconds"]} for i in slowest],
            "error_count": len(errors),
        },
        "notes": [],
    }
    prev = previous_baseline()  # read before saving, so never this run's file
    result["comparison"] = compare(result, prev)
    if errors:
        verdict = f"{len(errors)} problem(s) — see below."
    elif result["comparison"]["slower"]:
        verdict = "Works, but something got slower — see below."
    else:
        verdict = "All good — Bolt starts quickly."
    result["summary"]["verdict"] = verdict
    result["elapsed_sec"] = round(time.perf_counter() - started, 2)
    result["report"] = build_report(result)

    say("")
    say(result["report"])
    if save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        n = 2
        while results_file.exists():  # two runs in the same second
            results_file = RESULTS_DIR / f"baseline_{stamp.strftime('%Y%m%d_%H%M%S')}_{n}.json"
            n += 1
        tmp = results_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        tmp.replace(results_file)
        result["saved_to"] = str(results_file)
        say("")
        say(f"  Saved: {results_file}  ({result['elapsed_sec']} s)")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    repeats = DEFAULT_REPEATS
    if "--quick" in args:
        repeats = 1
    if "--repeats" in args:
        try:
            repeats = max(1, min(10, int(args[args.index("--repeats") + 1])))
        except Exception:
            print("Baseline unavailable: --repeats needs a number 1-10", file=sys.stderr)
            return 2
    as_json = "--json" in args
    res = run_baseline(repeats=repeats, save="--no-save" not in args, quiet=as_json)
    if as_json:
        print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
