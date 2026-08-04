# Bolt Process Roadmap

This is the living visual map for Bolt: what exists today, how the pieces connect,
and where the "Bolt has sovereignty, outside models provide counsel" architecture
fits later.

## Workspace Note

There are two Bolt workspaces in the current setup:

| Workspace | Role |
|---|---|
| `/Users/carter/developer/bolt` | The heavier local "big brother" workspace for larger work, heavier assets, and deeper development. |
| `/Users/carter/Library/Mobile Documents/com~apple~CloudDocs/Bolt` | The iCloud/shared workspace used to move decided work between Macs and keep the live cross-Mac setup in sync. |

When updating roadmap docs, make sure the change lands in the workspace that
matches the current task. This file is restored in the iCloud Bolt path because
that is part of the multi-Mac handoff flow.

## Current Bolt Runtime

```mermaid
flowchart TD
    User[Billy / Carter] --> Launcher[launch.py]
    Launcher --> Config[config.json]
    Launcher --> BrainProfile[Bolt_brain.md]
    Launcher --> Bot[bot.py main pipeline]

    Bot --> Watcher[modules/Watcher.py]
    Watcher --> Recordings[recordings/ folder]
    Recordings --> StableFile[stable new video file]

    StableFile --> Detect[Highlight_Detector.detect_highlights]
    Detect --> ClipGen[Clip_Generator.generate_clips]
    ClipGen --> Dedup[Clip_Deduplicator + Data/seen_clips.json]
    Dedup --> Titles[Title_Generator using creator profile]
    Dedup --> Subtitles[Subtitle_Generator / Whisper path]
    Titles --> Rank[Clip_Ranker score + tier]
    Subtitles --> Rank

    Rank --> Decision[Think_Learn_Decide]
    Decision --> Policy[allowlist / denylist]
    Policy --> Approval{approved?}
    Approval -->|yes| Format[Clip_Factory vertical format]
    Approval -->|no / later| Pending[Data/pending_proposals.json]

    Format --> Queue[Post_Queue / Data/ready_to_post.json]
    Queue --> Captions[caption .txt files]
    Queue --> Alerts[Peak-hour notifications]
    Queue --> Chat[Bolt_Chat trigger after real approved clip]
    Queue --> Voice[Bolt_Voice local alert]

    Decision --> Memory[Data/unified_memory.jsonl]
    Decision --> Model[Data/decision_model.json]
    Decision --> Audit[logs/decision_audit.log]
```

## What Bolt Owns Today

```mermaid
flowchart LR
    Core[Bolt Core Today] --> Memory[memory/ + Data/unified_memory.jsonl]
    Core --> Rules[config thresholds + action policy]
    Core --> Pipeline[clip pipeline]
    Core --> Queue[post queue]
    Core --> Audit[audit log]
    Core --> Feedback[feedback / outcomes]

    Claude[Claude title + memory recall] --> Titles[title ideas / recall answers]
    Titles --> Core

    Core --> DecisionGate[final local decision gate]
    DecisionGate --> LocalActions[queue clip, format clip, notify]
```

Bolt already owns the local action gate. The outside model path is currently used
for narrow help, mainly titles and memory recall. `Think_Learn_Decide` is local
and does not hand execution control to a cloud model.

## Desired Future Architecture

```mermaid
flowchart TD
    Request[User goal or new event] --> BoltCore[Bolt Core]

    subgraph BoltCoreBox[Bolt Core: sovereignty layer]
        Identity[identity + creator context]
        MemoryStore[long-term memory]
        Goals[current goals]
        PolicyEngine[permissions + safety policy]
        Router[model/tool router]
        Evaluator[evaluation + validation]
        FinalGate[final action gate]
    end

    BoltCore --> Identity
    BoltCore --> MemoryStore
    BoltCore --> Goals
    BoltCore --> PolicyEngine
    BoltCore --> Router

    Router --> CodeModel[coding specialist]
    Router --> ImageModel[image/video specialist]
    Router --> AudioModel[audio/transcription specialist]
    Router --> SearchTool[search / retrieval tool]
    Router --> LocalTools[local scripts + pipeline]

    CodeModel --> Proposal[proposals / drafts / outputs]
    ImageModel --> Proposal
    AudioModel --> Proposal
    SearchTool --> Proposal
    LocalTools --> Proposal

    Proposal --> Evaluator
    Evaluator --> FinalGate
    PolicyEngine --> FinalGate
    FinalGate -->|approved| Action[act locally]
    FinalGate -->|rejected| Reject[revise, ask user, or discard]

    Action --> Outcome[results + metrics]
    Reject --> Outcome
    Outcome --> MemoryStore
```

In this future version, outside models never become Bolt's controller. They are
specialists that return proposals. Bolt keeps the memory, policies, taste,
trust scores, action permissions, and final say.

## Roadmap From Here

```mermaid
flowchart TD
    A[Now: working clip pipeline] --> B[Clean repo + docs + config]
    B --> C[Stabilize memory schema]
    C --> D[Improve feedback logging from posted clips]
    D --> E[Add model/tool adapter interface]
    E --> F[Add router that chooses specialists]
    F --> G[Add evaluator per task type]
    G --> H[Track trust scores by model/tool]
    H --> I[Bolt Core chooses, validates, acts, and learns]
```

## Where We Are

| Layer | Status | Notes |
|---|---|---|
| Recording intake | Working | `Watcher.py` persists processed filenames. |
| Clip pipeline | Working | Detect, clip, dedup, title, subtitle, rank, format, queue. |
| Local decision gate | Started | `Think_Learn_Decide.py` proposes, checks policy, confirms, audits. |
| Memory | Started | Markdown memory exists; unified event memory exists. Retrieval needs more polish. |
| Feedback learning | Started | Decision model tracks feedback and outcomes; performance logging exists. |
| Outside model counsel | Partial | Claude is used for titles and memory recall, not full control. |
| Specialist router | Not built yet | Future layer for Claude/Grok/OpenAI/local tools/etc. |
| Evaluators | Not built yet | Future layer for tests, score checks, source checks, user taste checks. |
| Trust scores | Not built yet | Future model/tool performance memory. |

## Current Health Check

Last checked from the iCloud workspace on 2026-05-18:

- `/usr/local/bin/python3.11 scripts/verify.py` passes files, directories, config,
  environment, and module imports.
- `ffmpeg` is available for clip cutting and vertical formatting.
- The synced `.venv/` is not portable across Macs; it points at the other Mac's
  Homebrew Python path. Use a local Python/venv per Mac instead of relying on a
  synced virtualenv.
- `Data/ready_to_post.json` currently has historical queue rows whose media files
  are not present in this iCloud workspace. Peak alerts now ignore missing files
  and clips below the current score floor without deleting queue history.
- The iCloud workspace was locally slimmed down on this Mac without deleting the
  iCloud copy. The real heavy media archive is in `/Users/carter/developer/bolt`
  under `clips/` and `recordings/`.

## Operational Cleanup Map

```mermaid
flowchart TD
    LocalBig[/Users/carter/developer/bolt/] --> LocalClips[clips/ ~11G generated clips]
    LocalBig --> LocalRecordings[recordings/ ~64G source recordings]
    LocalBig --> LocalCode[active heavy-duty development]

    ICloud[/Users/carter/Library/Mobile Documents/com~apple~CloudDocs/Bolt/] --> SharedCode[cross-Mac shared code/docs]
    ICloud --> SharedQueue[Data/ready_to_post.json historical queue]
    ICloud --> Evicted[local downloads mostly evicted]

    SharedQueue --> QueueGate[Peak_Hour_Notifier alertable gate]
    QueueGate --> Existing{file exists locally?}
    Existing -->|yes| ScoreCheck{score >= min_post_score?}
    Existing -->|no| IgnoreMissing[ignore for alerts, keep history]
    ScoreCheck -->|yes| Alertable[eligible for peak alert]
    ScoreCheck -->|no| IgnoreLow[ignore for alerts, keep history]
```

## Design Principle

Bolt should not be a wrapper around another model's brain.

Bolt should be the system that remembers, routes, judges, validates, acts, and
learns. Outside models are counsel. Bolt keeps sovereignty.
