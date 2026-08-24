# Bolt

**Local-first AI content manager, producer, and business assistant for creators.**

Bolt handles the technical and operational side of content creation so you can stay focused on creating. It is built for real workflows around streaming, short-form video, product testing, and multi-platform publishing.

Think of it as a personal producer that runs locally on your machine.

## What Bolt Does

- **Automated Clip Pipeline** — Watches recordings and Twitch VODs, detects highlights, generates clips, titles, subtitles, vertical formats, thumbnails, and ranked queues.
- **Content Manager OS** — Tracks products across testing lanes, manages notes/drafts/status, and supports social packaging with human approval gates.
- **Direction-Finding Researcher** — Profile-driven research loop that helps answer “what should I be known for?” before production ramps.
- **Creator Command Center** — Turns goals into printable mission briefings with real constraints (time, budget, assets).
- **Voice & Conversation** — Hands-free voice engine, daily spoken briefings, Twitch chat personality with memory, and natural-language command routing.
- **Integrations** — OBS, Twitch, Streamlabs, Discord, Google Calendar/Gmail, local memory index, storage optimization, and multi-provider LLM support (xAI/Grok preferred, OpenAI, local Ollama).

Bolt is intentionally personal and opinionated. It is designed around an actual creator’s constraints, night-owl schedule, and long-term brand direction rather than generic automation.

## Core Features

### Clip & Media Pipeline
- Recording and VOD watching
- Audio-spike highlight detection with confidence gating and deduplication
- Clip generation, AI titles, subtitles, vertical formatting
- Thumbnail generation with smart frame selection
- Ranking tiers + recency-weighted learning
- Highlight reel compilation
- Storage optimization (compression, rotation, deduplication)

### Creator Operations
- Product/catalog tracking across lanes (tech/gaming, skincare/beauty, general product testing, etc.)
- Status workflow: testing → drafting → ready → posted
- Notes, drafts, performance logging
- Sponsor/affiliate prospecting support
- Social packaging with explicit approval gates

### Intelligence Layer
- Memory-aware daily and weekly briefings
- Local vector memory index
- Researcher role with keep/drop/maybe decisions
- Creator Command Center mission system
- Intent routing so natural language maps to real actions
- Multi-provider LLM (Grok / OpenAI / Ollama) with budget controls

### Voice & Interfaces
- Hands-free voice conversation (mic → STT → LLM → TTS)
- “Good Morning Bolt” spoken briefings
- Twitch chat personality with persistent memory
- Single CLI entry point (`bolt <command>`)
- Runtime doctor / verify / audit tools

## Quick Start

```bash
# Clone
git clone https://github.com/BillyThunderstorm/Bolt.git
cd Bolt

# Install (uv recommended)
uv sync

# Or with pip
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r Docs/requirements.txt   # or use the locked environment

# Configure
cp .env.example .env
# Edit .env with your keys (Twitch, xAI/OpenAI, etc.)

# Verify installation
bolt verify
# or
bolt doctor
Common Commands
Bashbolt help                    # Full command list
bolt morning                 # Spoken daily briefing
bolt manage next             # Next content manager actions
bolt research status         # Researcher status
bolt mission start "..."     # Create a mission
bolt recordings              # Process recordings
bolt briefing                # Generate briefing
See Core/modules/BOLT_COMMANDS.md for the complete reference.
Project Structure (High Level)
textBolt/
├── Core/                 # Main application code & modules
├── Data/                 # Memory, catalogs, queues, state
├── Docs/                 # Guides, status, architecture
├── bin/bolt              # Primary CLI entry point
├── scripts/              # Utility & maintenance scripts
├── media/                # Clips, verticals, samples
└── ...
Requirements

Python 3.11 or 3.12
macOS recommended (voice, OBS, local integrations)
Optional: OBS Studio, Twitch account, xAI / OpenAI / Ollama keys

Philosophy
Bolt is local-first. Your data, memory, and pipelines stay on your machine. Cloud LLMs are used only when you choose them, with budget controls and local fallbacks available.
It prioritizes reliability (per-clip failure isolation, quality gates, verification tools) and real creator constraints over flashy demos.
Status
Actively developed. See docs/PROJECT_STATUS.md and docs/upgrade/ for current build state and roadmaps.
License
[Add your preferred license here — e.g. MIT, or Private]
Author
Built by Billy Carter (@SimplyBilly_)

Navy veteran • Independent developer • Content creator

Bolt is a personal tooling project. It is not a commercial product.
