#!/usr/bin/env python3
"""
Hash-based Duplicate Detection for Bolt
=======================================
Detects duplicate media files using SHA256 hashing to prevent re-processing
and identify existing duplicates in media/clips and media/Recordings.

Post-reorg fix (11 Sep 2026): was ``parents[3]`` → ``/Users/carter`` with
legacy bare ``clips/`` / ``recordings/`` paths (every default scan missed
the real media tree). Now uses ``scripts/_paths.py``.

Soft-fail CLI wrapper (PARTIAL):
  bolt clip-dedupe status|list|run

Distinct from READY pipeline ``Core/modules/Clip_Deduplicator.py`` (pHash
during ``process_recording`` → ``Data/seen_clips.json``). This tool writes
``Data/media_hash_db.json``.

Usage:
  python3 scripts/clip_deduplicator.py
  python3 scripts/clip_deduplicator.py --dry-run
  python3 scripts/clip_deduplicator.py --scan media/clips
  python3 scripts/clip_deduplicator.py --check path/to/file.mp4
  python3 scripts/clip_deduplicator.py --clear-db
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    RECORDINGS_DIR,
    MEDIA_DIR,
)

# Backward-compatible aliases
PROJECT_ROOT = REPO_ROOT
HASH_DB_PATH = DATA_DIR / "media_hash_db.json"
DRY_RUN = False


def _resolve_clips_dir() -> Path:
    modern = CLIPS_DIR
    legacy = REPO_ROOT / "clips"
    if modern.is_dir():
        return modern
    if legacy.is_dir():
        return legacy
    return modern


def _resolve_recordings_dir() -> Path:
    modern = RECORDINGS_DIR
    legacy_lower = MEDIA_DIR / "recordings"
    legacy_root = REPO_ROOT / "recordings"
    if modern.is_dir():
        return modern
    if legacy_lower.is_dir():
        return legacy_lower
    if legacy_root.is_dir():
        return legacy_root
    return modern


def calculate_hash(file_path: Path, chunk_size: int = 8192):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except (IOError, OSError) as e:
        print(f"Error reading {file_path}: {e}")
        return None


def load_hash_db() -> dict:
    """Load existing hash database."""
    if HASH_DB_PATH.exists():
        try:
            with open(HASH_DB_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load hash database: {e}")
    return {"files": {}, "duplicates": []}


def save_hash_db(db: dict):
    """Save hash database to disk."""
    HASH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HASH_DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


def scan_directory(
    directory: Path, hash_db: dict, file_extensions: tuple = None
) -> dict:
    """Scan a directory for media files and calculate hashes."""
    results = {"scanned": 0, "new": 0, "duplicates": [], "errors": []}

    if not directory.exists():
        print(f"Directory does not exist: {directory}")
        return results

    print(f"\nScanning {directory}...")

    if file_extensions is None:
        file_extensions = (".mp4", ".mov", ".mkv", ".avi", ".jpg", ".jpeg", ".png")

    for file_path in directory.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in file_extensions:
            results["scanned"] += 1
            try:
                rel_path = str(file_path.relative_to(REPO_ROOT))
            except ValueError:
                rel_path = str(file_path)
            file_hash = calculate_hash(file_path)

            if file_hash is None:
                results["errors"].append(str(file_path))
                continue

            if file_hash in hash_db["files"]:
                existing_path = hash_db["files"][file_hash]
                if existing_path != rel_path:
                    results["duplicates"].append(
                        {
                            "file": rel_path,
                            "duplicate_of": existing_path,
                            "hash": file_hash[:16] + "...",
                        }
                    )
                    print(f"  DUPLICATE: {file_path.name}")
                    print(f"    -> Original: {existing_path}")
            else:
                hash_db["files"][file_hash] = rel_path
                results["new"] += 1

    return results


def find_duplicates(directories: list) -> dict:
    """Find all duplicates across multiple directories."""
    hash_db = load_hash_db()
    all_results = {
        "total_scanned": 0,
        "total_new": 0,
        "total_duplicates": 0,
        "duplicate_files": [],
        "by_directory": {},
    }

    for dir_path in directories:
        directory = Path(dir_path)
        if not directory.exists():
            continue

        results = scan_directory(directory, hash_db)
        all_results["total_scanned"] += results["scanned"]
        all_results["total_new"] += results["new"]
        all_results["total_duplicates"] += len(results["duplicates"])
        all_results["duplicate_files"].extend(results["duplicates"])
        all_results["by_directory"][str(directory)] = results

    if not DRY_RUN:
        save_hash_db(hash_db)
        print(f"\nHash database saved to: {HASH_DB_PATH}")
    else:
        print(f"\n[dry-run] would save hash database to: {HASH_DB_PATH}")

    return all_results


def check_file_for_duplicates(file_path: Path, hash_db: dict = None) -> bool:
    """Check if a single file is a duplicate. Returns True if duplicate."""
    if hash_db is None:
        hash_db = load_hash_db()

    file_hash = calculate_hash(file_path)
    if file_hash and file_hash in hash_db["files"]:
        existing = hash_db["files"][file_hash]
        try:
            rel_path = str(file_path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel_path = str(file_path)
        if existing != rel_path:
            print(f"Duplicate detected: {file_path.name}")
            print(f"  Original: {existing}")
            return True
    return False


def main():
    """Main entry point."""
    global DRY_RUN

    dirs_to_scan = []
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--dry-run":
            DRY_RUN = True
            print("DRY RUN MODE - No changes will be saved")
        elif arg == "--scan" and i + 1 < len(sys.argv):
            dirs_to_scan.append(Path(sys.argv[i + 1]))
            i += 1
        elif arg == "--check" and i + 1 < len(sys.argv):
            file_to_check = Path(sys.argv[i + 1])
            hash_db = load_hash_db()
            is_dup = check_file_for_duplicates(file_to_check, hash_db)
            sys.exit(0 if not is_dup else 1)
        elif arg in ("--clear-db", "--clear"):
            if Path(HASH_DB_PATH).exists():
                os.remove(HASH_DB_PATH)
                print(f"Hash database cleared: {HASH_DB_PATH}")
            else:
                print(f"No hash database at: {HASH_DB_PATH}")
            sys.exit(0)
        i += 1

    clips = _resolve_clips_dir()
    recordings = _resolve_recordings_dir()
    if not dirs_to_scan:
        dirs_to_scan = [clips, recordings]

    print("=" * 60)
    print("Bolt Duplicate Detection (SHA256 hash scan)")
    print("=" * 60)
    print(f"Repo root: {REPO_ROOT}")
    print(f"Scan directories: {[str(d) for d in dirs_to_scan]}")
    print(f"Hash database: {HASH_DB_PATH}")
    print(
        "Note: pipeline pHash dedupe is Core/modules/Clip_Deduplicator.py "
        f"→ Data/seen_clips.json (distinct from this tool)."
    )
    print()

    results = find_duplicates([str(d) for d in dirs_to_scan])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total files scanned: {results['total_scanned']}")
    print(f"New unique files: {results['total_new']}")
    print(f"Duplicates found: {results['total_duplicates']}")

    if results["total_duplicates"] > 0:
        print("\nDuplicate files:")
        for dup in results["duplicate_files"][:20]:
            print(f"  - {dup['file']}")
            print(f"    Duplicate of: {dup['duplicate_of']}")
        if results["total_duplicates"] > 20:
            print(f"  ... and {results['total_duplicates'] - 20} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
