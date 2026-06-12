# Creator Domains System Requirements

*System feature and data requirements for Bolt across 7 creator/business domains.*
*Last updated: 2026-06-08*

---

## Overview

Bolt is built to support Billy across multiple creator lanes. These requirements define what each domain needs from the system (features, memory, integrations, and quality gates) so Bolt can act as a true virtual teammate rather than a single-purpose clip bot.

Each domain below follows the same structure:
- **Purpose** — why this domain matters to Billy
- **Functional Requirements** — what Bolt must be able to do
- **Data / Memory Requirements** — what needs to be stored and recalled
- **Integration Points** — which modules or external services are involved
- **Quality Gates** — minimum standards before Bolt acts or suggests action

---

## 1. Content Creation

### Purpose
The core output layer. Bolt must help plan, draft, edit, and package content across short-form, long-form, and live formats without overwhelming Billy with options.

### Functional Requirements
- [ ] **Ideation Engine**: Generate one specific content idea at a time with a clear reason tied to Billy's current goals and past performance.
- [ ] **Hook Library**: Maintain a searchable set of proven hooks and openers per platform.
- [ ] **Format Awareness**: Know platform specs (TikTok 9:16, YouTube 16:9, Twitch live) and suggest the right format for the idea.
- [ ] **Cross-Platform Repurposing**: Propose how one piece of content can become multiple (e.g., stream → clip → post).
- [ ] **Script Assistance**: Provide talking points, not full scripts, unless explicitly requested.
- [ ] **Content Calendar**: Surface what to post next, not a dense calendar. One next step.
- [ ] **Voice Brainstorming**: Billy can talk to Bolt out loud to brainstorm ideas. Bolt listens, remembers the thread, and speaks back suggestions.

### Data / Memory Requirements
- Posted-content log with performance notes (views, engagement, what worked)
- Content idea backlog with platform, angle, and priority
- Hook templates tagged by platform and niche
- Voice/tone reference (what Billy sounds like, what he avoids)

### Integration Points
- `modules/Clip_Generator.py`, `modules/Clip_Ranker.py` — clip pipeline
- `modules/Title_Generator.py`, `modules/AI_Title_Generator.py` — titling
- `memory/content/content-ideas.md` — idea backlog
- `memory/content/posted-content-log.md` — results

### Quality Gates
- Every suggestion must tie back to Billy's review/testing angle (the brand).
- No generic lists. One idea, one reason, one next step.
- Hooks must feel like Billy's voice, not hype copy.

---

## 2. Assistant Productivity

### Purpose
Bolt should reduce friction in Billy's daily workflow: task management, focus, decision support, and preventing overwhelm.

### Functional Requirements
- [ ] **Daily Briefing**: Morning digest of queue status, storage, upcoming tasks, and one priority action.
- [ ] **Decision Support**: When Billy is stuck, ask clarifying questions and suggest one path forward.
- [ ] **Focus Mode**: Temporarily suppress non-urgent alerts during streaming or deep work.
- [ ] **Task Queue**: Track open tasks across domains and surface the highest-impact next task.
- [ ] **Overwatch**: Detect when Billy seems frustrated or stuck (via chat tone, repeated questions, or explicit signals) and respond with encouragement before solutions.
- [ ] **Learning Integration**: When Billy learns something new, capture it and suggest one way to apply it immediately.
- [ ] **Voice Conversation**: Billy can have a back-and-forth voice conversation with Bolt locally. Bolt listens via microphone, transcribes with Whisper, generates a personality-driven response, speaks it aloud through ElevenLabs (primary) or edge-tts/macOS fallback, and remembers the full thread persistently.

### Data / Memory Requirements
- Task state (open, in-progress, blocked, done) with domain tags
- Daily briefing history and what was acted on
- Frustration/stuck patterns (respect privacy, keep abstract)
- Learning notes with immediate application ideas

### Integration Points
- `modules/Think_Learn_Decide.py` — canonical intake/decision layer
- `modules/Google_Calendar.py` — schedule awareness
- `modules/Gmail_Briefing.py` — morning digest
- `memory/content/daily-briefing.md` — template and history

### Quality Gates
- Suggest one clear next step, never five options.
- Acknowledge frustration before solving.
- No empty productivity language ("just hustle harder").
- Explanations must include *why*, not just *what*.

---

## 3. Game and Tech Testing and Review

### Purpose
Gaming is a primary lane, but it serves the larger review/testing brand. Bolt must track games played, gear tested, and honest opinions while helping turn gameplay into content.

### Functional Requirements
- [ ] **Game Library**: Track titles played, genres, hours, and content potential.
- [ ] **Highlight Detection**: Detect stream-worthy moments (not just audio spikes) with game context.
- [ ] **Tech Review Shape**: Follow the reusable review structure (what it is, why tested, impression, what worked, what got in the way, who it is for, verdict).
- [ ] **Comparative Context**: Recall past games/gear to compare when relevant.
- [ ] **Content Pairing**: Suggest when a gameplay session or tech test is worth clipping, streaming, or reviewing.
- [ ] **Patch/Update Tracking**: Note when reviewed games or gear receive updates that might change the verdict.

### Data / Memory Requirements
- Game/gear catalog with status (playing, completed, shelved, reviewed)
- Review drafts and verdicts
- Highlight metadata with game context (map, mode, event type)
- Update/changelog notes for reviewed items

### Integration Points
- `modules/Highlight_Detector.py` — smart detection with context
- `modules/Game_Config.py` — game-specific settings
- `memory/content/game-testing.md` — catalog and reviews
- `memory/content/product-reviews.md` — gear crossover

### Quality Gates
- Reviews must be honest, not hype. If Billy did not like it, the tone should reflect that.
- Tech reviews must include real-world use, not spec recitation.
- Highlight detection must use game context, not just volume.

---

## 4. General Product Review and Testing

### Purpose
Billy's brand centers on honest, real-world assessments. This covers non-gaming products: skincare, household items, Amazon storefront products, and general gear.

### Functional Requirements
- [ ] **Product Catalog**: Track products being tested, queued for review, and already reviewed.
- [ ] **Test Journal**: Log real usage notes over time (day 1, day 7, day 30 where applicable).
- [ ] **Storefront Alignment**: Know which products are in Billy's Amazon Influencer storefront and tie reviews to purchase decisions.
- [ ] **Verdict Builder**: Assemble the reusable review shape from scattered notes.
- [ ] **Category Awareness**: Distinguish review style by category (skincare = routine context; tech = setup context; household = use-case context).
- [ ] **Red flags**: Flag products that seem unsafe, misleading, or not worth Billy's time.

### Data / Memory Requirements
- Product entries with category, source, test start date, verdict status
- Usage notes dated and tagged by product
- Storefront links and performance if available
- Honest opinions and takes (the "Billy voice" moments)

### Integration Points
- `modules/Skincare_Analyzer.py` — beauty/skincare-specific
- `modules/Amazon_Analyzer.py` — storefront and product parsing
- `memory/content/product-reviews.md` — master catalog
- `memory/content/beauty-skincare.md` — skincare subset

### Quality Gates
- Never fake excitement. If a product is mid, say it is mid.
- Always answer: "Who is this actually for?"
- Review must be grounded in Billy's actual experience.

---

## 5. Live Streaming

### Purpose
Twitch is a high-priority platform for real-time personality and community building. Bolt should assist before, during, and after streams without being distracting.

### Functional Requirements
- [ ] **Pre-Stream Setup**: Checklist (OBS, alerts, title, tags, category, peak-hour timing) with voice or chat confirmation.
- [ ] **Stream Monitor**: Watch stream health (dropped frames, chat activity, OBS connection) and alert quietly if something breaks.
- [ ] **Real-Time Chat Bot**: Respond to commands, answer FAQ, and trigger highlights at the right moment (not on every spike).
- [ ] **Engagement Prompts**: Occasionally suggest chat prompts or talking points when chat is quiet.
- [ ] **Clip Capture**: Mark timestamped highlights during stream for post-processing.
- [ ] **Post-Stream Wrap**: Summary of stream length, chat activity, highlights captured, and one suggested follow-up action.
- [ ] **Voice Companion Mode**: During IRL or non-game streams, Bolt can listen to Billy's voice and respond verbally via ElevenLabs for hands-free assistance.

### Data / Memory Requirements
- Stream history (date, length, category, peak viewers if known, notes)
- Chat command usage and response effectiveness
- Highlight timestamps tied to stream sessions
- Technical issues log and resolution

### Integration Points
- `modules/OBS_Integration.py` — scene and stream control
- `modules/Twitch_API.py`, `modules/Twitch_Stats.py` — stream data
- `modules/Stream_Monitor.py` — health checks
- `modules/Bolt_Chat.py` — chat bot
- `modules/Voice_Checklist.py` — pre-stream audio confirmation

### Quality Gates
- Alerts during stream must be quiet or whisper-level, never disruptive.
- Chat bot must not spam. One response per trigger, no loops.
- Post-stream wrap must fit in one screen or one voice summary.

---

## 6. AI Learning and Development

### Purpose
Billy is learning AI by building Bolt. This domain covers Billy's education, experiments, and the ongoing improvement of Bolt itself.

### Functional Requirements
- [ ] **Concept Tracker**: Log AI concepts learned, why they matter, and how they apply to Bolt.
- [ ] **Experiment Log**: Track local experiments (neural models, RAG, prompting) with results and next steps.
- [ ] **Build-in-Public Support**: Suggest content angles from AI learning moments.
- [ ] **Feature Roadmap**: Maintain a lightweight, prioritized list of Bolt features with rationale.
- [ ] **Local-First Guardrails**: Before suggesting paid APIs, propose local/free alternatives.
- [ ] **Teaching Mode**: When Billy asks how something works, explain step by step with context, not jargon.

### Data / Memory Requirements
- AI concepts with "what it is," "why it matters," "how it applies to Bolt"
- Experiment results (what was tried, what happened, what to try next)
- Feature ideas with priority, estimated effort, and blocker status
- Content angles from AI learning

### Integration Points
- `modules/LLM_Handler.py` — model usage and fallback logic
- `memory/content/ai-development.md` — learning notes
- `teaching/rag/` — RAG study materials
- `llm/` — local neural model experiments

### Quality Gates
- Explanations must be step by step. No jargon without context.
- Prefer local/free tools first.
- Keep experiments safe (no production risk without confirmation).
- Tie every concept back to Bolt or content.

---

## 7. Social Media Management

### Purpose
Cross-platform presence without burnout. Bolt should help schedule, post, track, and learn from social content across TikTok, Twitch, Instagram, X, and eventually YouTube.

### Functional Requirements
- [ ] **Queue Management**: Track clips and posts ready to go, with platform and scheduled time.
- [ ] **Peak Hour Awareness**: Know when Billy's audience is most active and suggest posting times.
- [ ] **Post Formatting**: Auto-format vertical clips, captions, and hashtags per platform.
- [ ] **Cross-Post Coordination**: Avoid posting the exact same content everywhere at once. Stagger or repurpose.
- [ ] **Analytics Notes**: Log what was posted, when, and any visible results. Do not require API access.
- [ ] **Community Touch**: Remind Billy to respond to comments or DMs on high-engagement posts.

### Data / Memory Requirements
- Post queue with platform, content reference, status, and intended time
- Peak hours per platform (can be estimated if no data)
- Posted-content log with performance notes
- Hashtag and caption templates per platform
- Comment/engagement reminders tied to posts

### Integration Points
- `modules/Post_Queue.py` — queue state
- `modules/Peak_Hour_Notifier.py` — timing alerts
- `modules/TikTok_Publisher.py`, `modules/Multi_Publisher.py` — posting
- `memory/content/posted-content-log.md` — results

### Quality Gates
- Never post without Billy approval unless explicitly configured otherwise.
- Captions must sound like Billy, not generic marketing copy.
- One platform at a time per suggestion. No "post everywhere" dumps.
- Respect rate limits and platform rules.

---

## Cross-Domain Priorities

When domains conflict, Bolt should prioritize in this order:

1. **Live Streaming** — real-time has the highest time sensitivity.
2. **Assistant Productivity** — if Billy is stuck or overwhelmed, everything else pauses.
3. **Content Creation / Social Media Management** — scheduled output is next.
4. **Game and Tech Testing / General Product Review** — research and testing happen around creation.
5. **AI Learning and Development** — continuous but never urgent unless it unblocks another domain.

## Success Metrics for Bolt

- Billy posts content weekly without feeling overwhelmed.
- Reviews and tests are tracked and retrievable.
- Stream setup feels automatic, not stressful.
- Billy learns one new AI concept per week and can explain it.
- Social posts are consistent across at least 2 platforms.
- Bolt's suggestions feel like a teammate, not a tool.
