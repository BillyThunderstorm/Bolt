Python 3.11.9 (v3.11.9:de54cf5be3, Apr  2 2024, 07:12:50) [Clang 13.0.0 (clang-1300.0.29.30)] on darwin
Type "help", "copyright", "credits" or "license()" for more information.
>>> #!/usr/bin/env python3
... """
... Filter the existing clip backlog by score.
... Moves low-scoring clips into clips/_low_score/ so you only review the good ones.
... """
... import os, shutil
... from pathlib import Path
... from modules.Clip_Ranker import _score_clip, _load_history
... 
... CLIPS_DIR = Path("clips")
... LOW_DIR = CLIPS_DIR / "_low_score"
... LOW_DIR.mkdir(exist_ok=True)
... 
... THRESHOLD = 65
... history = _load_history("Marvel Rivals")
... 
... # Build minimal clip-like objects from existing files
... class FakeClip:
...     def __init__(self, path):
...         self.output_file = str(path)
...         self.success = True
...         self.trigger = "highlight"  # default — adjust if you store metadata
...         self.confidence = 0.5
... 
... moved = 0
... kept = 0
... for clip in CLIPS_DIR.glob("*.mp4"):
...     fc = FakeClip(clip)
...     score, breakdown = _score_clip(fc, history)
...     if score < THRESHOLD:
...         shutil.move(str(clip), str(LOW_DIR / clip.name))
...         moved += 1
...     else:
...         kept += 1
...         print(f"  KEEP  {clip.name}  (score {score:.0f})")
... 
... print(f"\n✓ Kept {kept} clips above {THRESHOLD}")
... print(f"✗ Moved {moved} clips to {LOW_DIR}”)
