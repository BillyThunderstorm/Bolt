#!/usr/bin/env python3
"""
BOLT SYSTEM VERIFICATION & HEALTH CHECK
========================================
Run this script to verify Bolt is ready to operate.
Usage: python3 health_check.py
"""

import sys
from pathlib import Path
from datetime import datetime

def run_health_check():
    """Run full system health check."""
    
    print("\n" + "="*75)
    print(f" BOLT HEALTH CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*75 + "\n")
    
    checks_passed = 0
    checks_failed = 0
    checks_warning = 0
    
    # ========== CHECK 1: Files ==========
    print("[1] REQUIRED FILES")
    print("-" * 75)
    
    required_files = {
        "config.json": "Configuration",
        "Bolt_brain.md": "Creator profile",
        ".env": "Environment variables",
        "bot.py": "Main entry point",
        "launch.py": "Launcher script",
    }
    
    for fname, desc in required_files.items():
        path = Path(fname)
        if path.exists():
            size = path.stat().st_size
            print(f"  ✓ {fname:20} ({desc:25}) {size:,} bytes")
            checks_passed += 1
        else:
            print(f"  ✗ {fname:20} ({desc:25}) MISSING")
            checks_failed += 1
    
    # ========== CHECK 2: Directories ==========
    print("\n[2] REQUIRED DIRECTORIES")
    print("-" * 75)
    
    required_dirs = {
        "modules": "Pipeline modules",
        "recordings": "Input recordings",
        "clips": "Generated clips",
        "vertical_clips": "TikTok-formatted clips",
        "data": "Cache and rankings",
        "memory": "Persistent memory",
    }
    
    for dirname, desc in required_dirs.items():
        path = Path(dirname)
        if path.exists() and path.is_dir():
            count = len(list(path.glob("*")))
            print(f"  ✓ {dirname:20} ({desc:25}) {count:4} items")
            checks_passed += 1
        else:
            print(f"  ✗ {dirname:20} ({desc:25}) MISSING")
            checks_failed += 1
    
    # ========== CHECK 3: Python Modules ==========
    print("\n[3] PYTHON DEPENDENCIES")
    print("-" * 75)
    
    python_deps = {
        "openai": "OpenAI API",
        "librosa": "Audio analysis",
        "moviepy": "Video editing",
        "whisper": "Speech recognition",
        "twitchio": "Twitch bot",
        "cv2": "Video processing",
        "requests": "HTTP client",
        "dotenv": "Environment loading",
    }
    
    for module, desc in python_deps.items():
        try:
            __import__(module)
            print(f"  ✓ {module:20} ({desc:25})")
            checks_passed += 1
        except ImportError:
            print(f"  ✗ {module:20} ({desc:25}) NOT INSTALLED")
            checks_failed += 1
    
    # ========== CHECK 4: Bolt Modules ==========
    print("\n[4] BOLT PIPELINE MODULES")
    print("-" * 75)
    
    bolt_modules = [
        "modules.Config_Loader",
        "modules.Highlight_Detector",
        "modules.Clip_Generator",
        "modules.Title_Generator",
        "modules.Subtitle_Generator",
        "modules.Clip_Ranker",
        "modules.Clip_Factory",
        "modules.Think_Learn_Decide",
        "modules.Bolt_Chat",
        "modules.Bolt_Memory",
        "modules.LLM_Handler",
    ]
    
    for module in bolt_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
            checks_passed += 1
        except Exception as e:
            print(f"  ✗ {module}")
            print(f"    → {str(e)[:60]}")
            checks_failed += 1
    
    # ========== CHECK 5: Configuration ==========
    print("\n[5] CONFIGURATION")
    print("-" * 75)
    
    try:
        from modules.Config_Loader import load_config
        config = load_config()
        print(f"  ✓ config.json loads successfully")
        print(f"    • Game: {config.get('game')}")
        print(f"    • Min score: {config.get('min_post_score')}")
        print(f"    • Max clips/session: {config.get('max_clips_per_session')}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ config.json error: {e}")
        checks_failed += 1
    
    # ========== CHECK 6: Environment ==========
    print("\n[6] ENVIRONMENT VARIABLES")
    print("-" * 75)
    
    import os
    env_checks = {
        "OPENAI_API_KEY": "LLM API key (required for chat & memory)",
        "TWITCH_CHANNEL": "Twitch channel (required for chat)",
        "TWITCH_BOT_TOKEN": "Twitch bot OAuth (required for chat)",
    }
    
    for key, desc in env_checks.items():
        val = os.getenv(key, "").strip()
        if val and not val.startswith("sk_your"):
            print(f"  ✓ {key:25} Set")
            checks_passed += 1
        else:
            if "required" in desc:
                print(f"  ⚠ {key:25} Not set → {desc}")
                checks_warning += 1
            else:
                print(f"  • {key:25} Not set (optional)")
    
    # ========== CHECK 7: API Connectivity ==========
    print("\n[7] API CONNECTIVITY")
    print("-" * 75)
    
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and not openai_key.startswith("sk_your"):
        print(f"  ✓ OPENAI_API_KEY configured")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            # Don't make actual API call, just verify client creation
            print(f"  ✓ OpenAI client initialized successfully")
            checks_passed += 1
        except Exception as e:
            print(f"  ✗ OpenAI client error: {e}")
            checks_warning += 1
    else:
        print(f"  • OPENAI_API_KEY not set (LLM features will use fallbacks)")
    
    # ========== SUMMARY ==========
    print("\n" + "="*75)
    print(" HEALTH CHECK SUMMARY")
    print("="*75)
    
    total_checks = checks_passed + checks_failed + checks_warning
    
    print(f"\nResults:")
    print(f"  ✓ Passed:   {checks_passed}/{total_checks}")
    print(f"  ⚠ Warnings: {checks_warning}/{total_checks}")
    print(f"  ✗ Failed:   {checks_failed}/{total_checks}")
    
    if checks_failed == 0 and checks_warning <= 1:
        print(f"\n✓ SYSTEM READY")
        print(f"\nTo start Bolt:")
        print(f"  python3 launch.py")
        return 0
    elif checks_failed == 0:
        print(f"\n⚠ SYSTEM OPERATIONAL (with warnings)")
        print(f"\nTo start Bolt:")
        print(f"  python3 launch.py")
        print(f"\nNote: Configure missing env vars for full functionality")
        return 0
    else:
        print(f"\n✗ SYSTEM NOT READY")
        print(f"\nFix the failed checks before running Bolt.")
        return 1

if __name__ == "__main__":
    exit_code = run_health_check()
    print("\n" + "="*75 + "\n")
    sys.exit(exit_code)
