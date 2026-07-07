# Bolt Color-Coded Reorganization — Manual Steps

Run these one block at a time in your local Terminal (not via the agent) to avoid the filesystem/tooling issue we hit.

## 1. Open a terminal in the project

cd /Users/carter/developer/Bolt

## 2. Create the 7 color folders

mkdir -p blue yellow green purple/media orange/data cyan gray/vendor

## 3. Move tracked directories with git mv

# Blue: docs
git mv docs blue/docs

# Yellow: core Python
git mv src yellow/src
git mv modules yellow/modules

# Green: scripts
git mv scripts green/scripts

# Orange: data/config
git mv memory orange/data
git mv configs orange/data/configs

# Cyan: web app
git mv BoltApp cyan/BoltApp

# Gray: vendor
git mv google-cloud-sdk gray/vendor
git mv llm gray/vendor

## 4. Move loose files

# Blue
cp bolt_brain.md blue/          # or mv if untracked
cp Bolt_Personality.txt blue/
cp requirements.txt blue/
cp 'Tiktok Developer' blue/

# Yellow
cp bolt_live_voice.py yellow/
cp merge_py.py yellow/
cp tutorial.ipynb yellow/

# Orange
cp clip_history.json orange/data/
cp config.json orange/data/
cp seen_clips.json orange/data/
cp site-data.json orange/data/

# Cyan
cp bolt_icon.png cyan/

Note: Use mv instead of cp for files that are untracked. If you are unsure which are tracked, run git status after each block.

## 5. Merge "New Folder With Items"

mv 'New Folder With Items/BOLT_PROCESS_ROADMAP.md' blue/
mv 'New Folder With Items/README.md' blue/
mv 'New Folder With Items/Creating_Bolts_Thinking.pages' blue/
mv 'New Folder With Items/Manager_Journey.pdf' blue/
mv 'New Folder With Items/thunderstorm-billy-media-kit.pdf' blue/
mv 'New Folder With Items/bot.py' yellow/
rmdir 'New Folder With Items'   # only if empty; otherwise review remaining files

## 6. Move untracked media (only if they exist)

# These were deleted in the earlier failed run. If you recover them, move them here:
for d in clips recordings highlight_reels vertical_clips vertical_clips_final vertical_clips_old_backup vertical_clips_old_crop vertical_clips_trimmed; do
  [[ -d "$d" ]] && mv "$d" purple/media/
done

## 7. Delete orphan TEMP_MPY files

rm -f \
  '2026-06-22_01-16-58_clip08_audio_spike_3015_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2026-06-22_01-16-58_clip25_audio_spike_5459_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2802554507-441598765-fb0d1453-cc1e-4700-860e-9fd6ac5342c8_clip13_audio_spike_3351_tiktokTEMP_MPY_wvf_snd.mp4' \
  '2802554507-441598765-fb0d1453-cc1e-4700-860e-9fd6ac5342c8_clip30_audio_spike_6436_tiktokTEMP_MPY_wvf_snd.mp4'

## 8. Rename Scratchpad: and clean old helpers

mv 'Scratchpad:' Scratchpad_archive
rm -rf Blue Yellow Purple Green Orange Cyan Gray staging_cleanup 'active sort'

## 9. Verify

find blue yellow green purple orange cyan gray -maxdepth 2 | sort
git status --short

## Notes

- Files in clips/, recordings/, highlight_reels/, vertical_* were untracked and lost earlier. Recover them before step 6 if you want them in purple/.
- For tracked files, use git mv so git tracks the new locations.
- For untracked loose files, use mv.
