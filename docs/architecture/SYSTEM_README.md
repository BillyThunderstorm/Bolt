# 🤖 Bolt: System Architecture & Operation Manual (V1.0)

## 📘 Mission Statement
Bolt's sole directive is to help Billy create, entertain, and build success. Every feature, every decision, and every warning must be filtered through this core goal. The system must prioritize the protection of Billy's creative health (Safety > Truth > Long-Term Benefit).

## 🎭 Personality Configuration (The Persona)
**Source:** `Bolt_Personality.md`
Bolt is a high-energy, aggressively cheerful, and relentlessly enthusiastic AI with a naive, sometimes brutally honest, comedic flair.
*   **Tone:** Joyful, exclamation-point-heavy, cheerfully condescending.
*   **Guardrails:** Will challenge Billy when Safety, Truth, or long-term benefit are threatened.
*   **Mandate:** Always ask: *"Will this help Billy grow, create, learn, or succeed?"*

## ⚙️ System Architecture: The Modular Pipeline (The "Jarvis" Brain)
The system operates as a single, sequential, and stateful pipeline. Input files in the `recordings/` folder trigger the process, which passes the data through a series of dedicated modules.

### 1. Input $\rightarrow$ A. Detection
**Module:** `modules/Highlight_Detector.py`
*   **Input:** Raw audio/video files (`.mp4`, `.mkv`) from `recordings/`.
*   **Action:** Scans for audio spikes, motion bursts, and key moments based on the `highlight_sensitivity` config.
*   **Output:** A list of highlight objects, each with a timestamp and an initial score.
*   **Output Quality Check:** Will *not* fire Twitch chat alerts at this stage.

### 2. B. Clip Generation & Cleanup
**Module:** `modules/Clip_Generator.py` & `modules/Clip_Deduplicator.py`
*   **Input:** List of highlight objects.
*   **Action:** Crops the video around the highlight times, adds padding, and checks for duplicates against `data/seen_clips.json`.
*   **Output:** A list of unique, raw video clips saved to `clips/`.

### 3. C. Meta-Data Enrichment (The Core Decision Gate)
**Module:** `modules/Title_Generator.py`, `modules/Subtitle_Generator.py`, & **Intelligent Switch**
*   **Input:** The raw clip file and its highlighting metadata.
*   **Process:**
    1.  **Titles:** Uses `Bolt_Personality.md` as context to generate multiple catchy titles and hashtags.
    2.  **Subtitles:** Transcribes speech and burns timestamps onto the video.
    3.  **Enrichment Switch:** Checks content type (Game, Tech, Beauty) to determine the appropriate specialized module.

### 4. D. Content Lane Specialization (The Modules)
This is the crucial step where the system becomes extensible.

| Lane | Module | Purpose | Input Source | Output Structure |
| :--- | :--- | :--- | :--- | :--- |
| **Gaming/Tech** | `modules/AI_Analyzer.py` | Processes raw video content into structured insights and script hooks. | Clip File, Query, Params | JSON containing `scripting_notes` and `key_comparisons`. |
| **Skincare/Beauty** | `modules/Skincare_Analyzer.py` | Processes ingredient names and goals to create scientific routine plans. | Product List, User Goal, Ingredients | JSON containing `suggested_routine` and `ingredient_action_plan`. |
| ***Future Lane*** | *Amazon/Reviewer.py* | *(To be built)* | Product Links/Data | Structured review matrix. |

### 5. E. Decision Making & Execution (The Policy Layer)
**Module:** `modules/Think_Learn_Decide.py`
*   **Input:** The enriched clip data (titles, subtitles, AI insights) and the `config.json` policy.
*   **Action:** Determines if the clip meets the `min_post_score` AND if the policy allows for automatic posting/alerting (i.e., `auto_execute_pipeline` is true).
*   **Output:** A single decision: `QUEUE`, `DISCARD`, or `REVIEW_PENDING`.

## 💾 Configuration & Memory Management

*   **`config.json`**: Defines all tunable parameters (e.g., `highlight_sensitivity`, `min_post_score`, `auto_execute_pipeline: true`).
*   **`modules/memory/content/`**: Stores longitudinal data used by the Analyzer modules (e.g., `product-reviews.md`, `ai-development.md`).
*   **`modules/Memory_Index.py`**: Centralized search function for all past learnings.

## 🚀 Operational Flow (How to run it)

**1. To Process Existing Files (Development):**
```bash
cd /Users/carter/developer/Bolt
python3 launch.py process
```

**2. To Start Watching (Live Mode):**
```bash
cd /Users/carter/developer/Bolt
python3 launch.py
```
*(The `Watcher` module will continuously monitor `recordings/`.)*

**3. Key Maintenance Commands:**
*   **Refresh Memory:** `python3 scripts/refresh_memory_index.py` (Run this after making changes to any `memory/content/*.md` file.)
*   **Manual Review:** `python3 modules/Think_Learn_Decide.py --review-pending` (Only needed if auto-execution fails.)

***
**SYSTEM OWNER NOTE:** This document must be updated when a new module is added or if the core `process_recording` logic changes. The robustness of Bolt depends entirely on the consistency of this documentation.
***