Bolt is a local-first AI content manager, producer, and business assistant built for creators who live on stream, short-form platforms, and product testing.
It handles the technical and operational side of content creation so you can stay focused on the actual work. Think of it as a personal Jarvis tailored for Twitch/TikTok/YouTube pipelines, product reviews, skincare/beauty expansion, Amazon Influencer storefront management, sponsor research, and day-to-day creator operations.
Core Capabilities
Automated Clip Pipeline

Watches local recordings and Twitch VODs
Detects highlights via audio spikes with hard confidence gating and deduplication
Generates clips, AI-powered titles (profile-aware), subtitles, and vertical (TikTok-style) formats
Ranks clips with tiered scoring + recency-weighted learned boost
Compiles highlight reels
Auto-generates thumbnails with smart frame selection
Queues high-quality clips and notifies at peak hours (Discord/voice)

Content Manager OS

Full product/catalog tracking across lanes (tech/gaming, skincare/beauty, Amazon Influencer, etc.)
Status tracking (testing → drafting → ready → posted)
Notes, drafts, shipping logs, and multi-platform performance logging
Storefront feature prioritization and sponsor/affiliate prospecting
Social packaging with explicit human approval gates

Direction-Finding Researcher

Profile-driven research loop (C5/C6/C7 decision framework)
Answers “what should I be known for?” before ramping production
Keeps a research log that surfaces in daily briefings
Supports keep/drop/maybe decisions with rationale

Creator Command Center

Turns high-level goals into printable mission briefings (check-ins → options → checklists)
Respects real constraints (time, budget, assets, restrictions)
Planning only — nothing posts or purchases without approval

Voice & Conversation Layer

Hands-free voice conversation engine (mic + speech-to-text + LLM + TTS)
Daily “Good Morning Bolt” spoken briefings with memory-aware context, live queue counts, and research notes
Twitch chat personality bot with persistent conversation memory
Local queue and memory commands via chat or voice

Integrations & Runtime

OBS Studio (scene control, monitoring)
Twitch (VODs, chat, stats)
Streamlabs events
Discord notifications
Google Calendar + Gmail hooks
Apple Reminders / SMS / email delivery for briefings
Local memory index (vector retrieval) for creator vision, lane notes, decisions, and performance history
Storage optimization (compression, rotation, deduplication, monitoring with alerts)

LLM Flexibility

Multi-provider support (xAI/Grok preferred, OpenAI, local Ollama)
Intent routing so natural language maps to real Bolt actions
Budget-aware mode switching (local / light / full)

Architecture Highlights

Python-first, local-first design (macOS-optimized, night-owl friendly)
Single CLI entry point (bolt <command>) with rich subcommands
Modular Core (pipeline, manager, researcher, conversation, decision engine)
Persistent memory and creator profile that guide ranking, titles, research, and briefings
Heavy emphasis on reliability: per-clip failure isolation, quality gates, verification/doctor commands, and extensive test coverage

Bolt is intentionally personal and opinionated — it is built around a real creator’s workflow, constraints, and long-term brand direction rather than generic automation. It is under active development with a strong focus on making the “what should I do next?” decision clear and low-friction every day.
