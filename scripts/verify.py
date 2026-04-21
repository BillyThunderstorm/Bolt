#!/usr/bin/env python3
"""
Verification script to test all components of the streaming assistant
Run this to ensure everything is configured correctly
"""

import os
import sys
import json
from pathlib import Path

def check_files():
    """Check if all required files exist"""
    print("📋 Checking project files...")
    
    required_files = [
        'bot.py',
        'config.json',
        '.env.example',
        'requirements.txt',
        'README.md',
        'SETUP_GUIDE.md',
        'PROJECT_STATUS.md',
    ]
    
    required_modules = [
        'modules/Watcher.py',
        'modules/Highlight_Detector.py',
        'modules/Clip_Generator.py',
        'modules/Subtitle_Generator.py',
        'modules/AI_Title_Generator.py',
        'modules/Clip_Ranker.py',
        'modules/TikTok_Poster.py',
        'modules/OBS_Integration.py',
        'modules/Clip_Factory.py',
        'modules/Gaming_Highlights.py',
    ]
    
    missing = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
            print(f"  ❌ {file}")
        else:
            print(f"  ✓ {file}")
    
    for file in required_modules:
        if not os.path.exists(file):
            missing.append(file)
            print(f"  ❌ {file}")
        else:
            print(f"  ✓ {file}")
    
    return len(missing) == 0

def check_directories():
    """Check if required directories exist"""
    print("\n📁 Checking directories...")
    
    directories = [
        'recordings',
        'clips',
        'vertical_clips',
        'modules',
        'assets',
    ]
    
    all_exist = True
    for dir in directories:
        if not os.path.isdir(dir):
            print(f"  ⚠️  {dir}/ (creating...)")
            os.makedirs(dir, exist_ok=True)
        else:
            print(f"  ✓ {dir}/")
    
    return True

def check_config():
    """Check configuration"""
    print("\n⚙️  Checking configuration...")
    
    if not os.path.exists('config.json'):
        print("  ❌ config.json not found")
        return False
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        required_keys = [
            'game',
            'auto_rank',
            'auto_format_tiktok',
            'highlight_sensitivity',
        ]
        
        for key in required_keys:
            if key in config:
                print(f"  ✓ {key}: {config[key]}")
            else:
                print(f"  ❌ {key} missing")
                return False
        
        return True
    except Exception as e:
        print(f"  ❌ Error reading config: {e}")
        return False

def check_env():
    """Check environment setup"""
    print("\n🔐 Checking environment...")
    
    if not os.path.exists('.env'):
        print("  ⚠️  .env file not found (copy from .env.example)")
        print("  Create with: cp .env.example .env")
    else:
        print("  ✓ .env file exists")
    
    env_vars = [
        'OBS_HOST',
        'OBS_PORT',
        'TIKTOK_USERNAME',
        'TIKTOK_PASSWORD',
    ]
    
    print("  Suggested environment variables:")
    for var in env_vars:
        if os.getenv(var):
            print(f"  ✓ {var} set")
        else:
            print(f"  - {var} (not set)")

def test_imports():
    """Test if all modules can be imported"""
    print("\n🔌 Testing module imports...")
    
    modules = [
        'modules.Watcher',
        'modules.Highlight_Detector',
        'modules.Clip_Generator',
        'modules.Subtitle_Generator',
        'modules.Clip_Factory',
        'modules.Gaming_Highlights',
    ]
    
    # New modules
    new_modules = [
        'modules.AI_Title_Generator',
        'modules.Clip_Ranker',
        'modules.TikTok_Poster',
        'modules.OBS_Integration',
    ]
    
    all_ok = True
    
    print("  Core modules:")
    for module in modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except Exception as e:
            print(f"  ❌ {module}: {e}")
            all_ok = False
    
    print("  New modules:")
    for module in new_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except Exception as e:
            print(f"  ❌ {module}: {e}")
            all_ok = False
    
    return all_ok

def main():
    """Run all checks"""
    print("🎮 Streaming AI Assistant - Verification Check")
    print("=" * 50)
    
    checks = [
        ("Files", check_files),
        ("Directories", check_directories),
        ("Configuration", check_config),
        ("Environment", check_env),
        ("Module Imports", test_imports),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n❌ Error during {name} check: {e}")
            results[name] = False
    
    print("\n" + "=" * 50)
    print("📊 Verification Summary")
    print("=" * 50)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "⚠️  WARNING"
        print(f"{status}: {name}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All checks passed! Ready to run:")
        print("   python bot.py")
    else:
        print("⚠️  Some checks failed. See above for details.")
        print("\nQuick fixes:")
        print("  1. Run: chmod +x setup.sh")
        print("  2. Run: ./setup.sh")
        print("  3. Configure .env and config.json")
        print("  4. Run: python bot.py")
    
    print("=" * 50)
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
