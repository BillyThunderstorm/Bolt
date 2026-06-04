# Loose Document Cleanup

Implemented on 2026-06-02 for `/Users/carter/developer/Bolt`.

## Filed Locations

- `DEBUG_REPORT.md` -> `docs/reports/DEBUG_REPORT.md`
- `SYSTEM_README.md` -> `docs/architecture/SYSTEM_README.md`
- `Bolt_Personality.md` -> `memory/context/bolt-personality.md`
- `RAG_Study.rtf` -> `teaching/rag/RAG_Study.rtf`
- `RAG_Progress/` -> `teaching/rag/RAG_Progress/`
- `Upgrade/` -> `docs/upgrade/`
- `briefings/daily/` remains the canonical daily briefing output folder

## Removed

- `BillyThunderstorm-site/` was removed intentionally, including nested duplicate copies.

## Runtime Notes

- `Daily_Briefing.py` stayed at repo root so existing `launch.py` imports remain unchanged.
- `.env.backup` and launcher log files should remain local-only and ignored.
