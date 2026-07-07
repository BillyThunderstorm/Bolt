#!/usr/bin/env bash
# Bolt color-coded reorganization script
# Run from inside /Users/carter/developer/Bolt
# Usage: bash reorganize_bolt.sh --dry-run   (preview)
#        bash reorganize_bolt.sh             (execute)

set -euo pipefail

ROOT="/Users/carter/developer/Bolt"
DRY="${1:-}"

cd "$ROOT" || { echo "Cannot cd to $ROOT"; exit 1; }

if [[ "$DRY" == "--dry-run" ]]; then
  echo ">>> DRY RUN: no files will be moved"
  ACTION="echo [DRY]"
else
  echo ">>> EXECUTING moves"
  ACTION=""
fi

run() {
  if [[ -n "$ACTION" ]]; then
    echo "$ACTION $*"
  else
    echo "[RUN] $*"
    "$@"
  fi
}

# Create color folders
for c in blue yellow green purple orange cyan gray; do
  run mkdir -p "$c"
done

# Blue: docs + loose text/markdown/rtf/pdf
run git mv docs blue/docs
run mv bolt_brain.md blue/
run mv Bolt_Personality.txt blue/
run mv requirements.txt blue/
run mv 'Tiktok Developer' blue/

# Yellow: core Python
run git mv src yellow/src
run git mv modules yellow/modules
run mv bolt_live_voice.py yellow/
run mv merge_py.py yellow/
run mv tutorial.ipynb yellow/

# Green: scripts
run git mv scripts green/scripts

# Orange: data/config
run git mv memory orange/data
run git mv configs orange/data/configs
run mv clip_history.json orange/data/
run mv config.json orange/data/
run mv seen_clips.json orange/data/
run mv site-data.json orange/data/

# Purple: media (untracked dirs that were lost in earlier attempt will be skipped)
for d in clips recordings highlight_reels \
         vertical_clips vertical_clips_final vertical_clips_old_backup \
         vertical_clips_old_crop vertical_clips_trimmed; do
  if [[ -d "$d" ]]; then
    run mv "$d" "purple/media/$d"
  else
    echo "[SKIP] $d not found"
  fi
done

# Cyan: web app
run git mv BoltApp cyan/BoltApp
run mv bolt_icon.png cyan/

# Gray: vendor
run git mv google-cloud-sdk gray/vendor
run git mv llm gray/vendor

# New Folder With Items -> merge to blue/yellow
NF='New Folder With Items'
if [[ -d "$NF" ]]; then
  for f in "$NF/BOLT_PROCESS_ROADMAP.md" "$NF/README.md" \
           "$NF/Creating_Bolts_Thinking.pages" \
           "$NF/Manager_Journey.pdf" \
           "$NF/thunderstorm-billy-media-kit.pdf"; do
    [[ -e "$f" ]] && run mv "$f" blue/
  done
  [[ -e "$NF/bot.py" ]] && run mv "$NF/bot.py" yellow/
  run rm -rf "$NF"
fi

# Delete orphan TEMP_MPY mp4 files
for f in \
  '2026-06-22_01-16-58_clip08_audio_spike_3015_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2026-06-22_01-16-58_clip25_audio_spike_5459_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2802554507-441598765-fb0d1453-cc1e-4700-860e-9fd6ac5342c8_clip13_audio_spike_3351_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2802554507-441598765-fb0d1453-cc1e-4700-860e-9fd6ac5342c8_clip30_audio_spike_6436_tiktokTEMP_MPY_wvf_snd.mp4'; do
  [[ -f "$f" ]] && run rm -f "$f"
done

# Rename Scratchpad:
if [[ -d 'Scratchpad:' ]]; then
  run mv 'Scratchpad:' Scratchpad_archive
elif [[ -d 'Scratchpad' && ! -d 'Scratchpad_archive' ]]; then
  run mv 'Scratchpad' Scratchpad_archive
fi

# Remove old uppercase color/staging leftovers
for d in Blue Yellow Purple Green Orange Cyan Gray staging_cleanup 'active sort'; do
  [[ -d "$d" ]] && run rm -rf "$d"
done

echo ""
echo ">>> Done."
if [[ -n "$ACTION" ]]; then
  echo "Dry run complete. Re-run without --dry-run to execute."
else
  echo "Verify with: cd $ROOT && git status --short"
fi
