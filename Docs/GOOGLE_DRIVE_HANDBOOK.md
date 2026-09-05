# Bolt Creator OS — Google Drive handbook (pointer)

This is a **local pointer**, not a second handbook. The live journal, briefing, todo, and how-to live in Google Drive so William and Bolt share one copy.

Canonical IDs are also in `Core/config.json` → `google_drive_handbook`. Do not put Google OAuth secrets in the repo.

## Start here

| What | Where |
|------|--------|
| Root folder **Bolt Creator OS** | https://drive.google.com/drive/folders/1GZ93zTznYK97Nv9Do5bidLOd9Im1J1XK |
| START HERE | https://docs.google.com/document/d/1u3dRveLkOBsfSpuBXKeFbfj7tVH3EhjZJr-aic5bxjw/edit |
| How-to handbook (native Google Doc, in `00_Brand`) | https://docs.google.com/document/d/12idgxLR-OzcOyCC6mDQwqmOnZQDuMIZIJCwwMnm_krg/edit |
| Shared Journal (in `02_Daily_Operations`) | https://docs.google.com/document/d/1paZNFGea-RBAwQ5YMxpuXN8OBRH7R33RAkakYZ23Tfw/edit |
| 2026-08-31 Daily Log | https://docs.google.com/document/d/1RwUyRhjPGjpugrHLkUvyQAog09YMadiMebeZCn0dlLQ/edit |
| Original Word file (archive, in `00_Brand`) | https://drive.google.com/file/d/138abBq9A-zWY0MZCBeyXxRCuwtsjxjeK/view |

## Folder map

| Folder | Drive ID | URL |
|--------|----------|-----|
| 00_Brand | `1YHZSqjoP7JPNP7NPChdgCRQH80advpHj` | https://drive.google.com/drive/folders/1YHZSqjoP7JPNP7NPChdgCRQH80advpHj |
| 01_Strategy | `1tvdBRHvkDeRFaF0zB8ieyJnKwFAp3dqH` | https://drive.google.com/drive/folders/1tvdBRHvkDeRFaF0zB8ieyJnKwFAp3dqH |
| 02_Daily_Operations | `1wanq-qUUGc4qF-uqtqnajAwLd877qSQ4` | https://drive.google.com/drive/folders/1wanq-qUUGc4qF-uqtqnajAwLd877qSQ4 |
| 03_Recordings | `1gg0mwaptH0IY91L-_dJscM4b14TxTElZ` | https://drive.google.com/drive/folders/1gg0mwaptH0IY91L-_dJscM4b14TxTElZ |
| 04_Clips_In_Progress | `1KvcwqLO8MeGz_mr4R1RJoqYdpmibNYTe` | https://drive.google.com/drive/folders/1KvcwqLO8MeGz_mr4R1RJoqYdpmibNYTe |
| 05_Ready_To_Post | `1tTOf1h3b_PEU3VQjX_zAJAfkvCqJNFSU` | https://drive.google.com/drive/folders/1tTOf1h3b_PEU3VQjX_zAJAfkvCqJNFSU |
| 06_Learnings | `1oPmHtmY28r_fPjr5cYwiYb5BUDdQCWLH` | https://drive.google.com/drive/folders/1oPmHtmY28r_fPjr5cYwiYb5BUDdQCWLH |
| 07_Code_And_System | `1KElSeoxBkUJTyDx8CBIm-BH1_XxSjDzy` | https://drive.google.com/drive/folders/1KElSeoxBkUJTyDx8CBIm-BH1_XxSjDzy |

## Daily loop (William + Bolt)

Local Bolt still writes `Docs/briefings/daily/latest_morning.md` via `bolt briefing` / `bolt morning`. Treat Drive as the **shared** journal, not a parallel markdown handbook.

1. **Morning** — run `bolt briefing` (or `bolt morning`). Bolt writes `Docs/briefings/daily/latest_morning.md` **and**, when Drive OAuth is present, appends a **Bolt briefing** section to today's Daily Log in `02_Daily_Operations` (creates the Doc if missing; never duplicates the day's file). Open **START HERE**, then today's Daily Log and the **Shared Journal**.
2. **During the day** — todos and how-to live in the native handbook Doc (`00_Brand`) and the Shared Journal. Do not duplicate them into `Docs/`.
3. **Evening** — write the day's log in `02_Daily_Operations` (new dated Daily Log, or append the Shared Journal). Put lasting lessons in `06_Learnings`.
4. **Code/system notes** that must stay in git still go under `Docs/` and `Data/MEMORY.md`. Point at Drive; do not copy the whole handbook down.

## What Bolt can do with Google today

| Surface | Status |
|---------|--------|
| Google Calendar | Read-only client exists (`Core/modules/Google_Calendar.py`). Needs `Core/credentials.json` + `data/google_token.json`. |
| Gmail (briefing) | Read-only client exists (`Core/modules/Gmail_Briefing.py`). Needs the same credentials file + a Gmail token. |
| YouTube stats | Separate OAuth in local `.env` (`YOUTUBE_*`). Not Drive/Docs. |
| Google Docs / Drive | **Daily Log write is implemented** (`Core/modules/Google_Drive_Handbook.py`). `bolt briefing` / `bolt morning` find-or-create `YYYY-MM-DD Daily Log` in `02_Daily_Operations` and append a Bolt briefing section (Docs API `insertText`). Same desktop OAuth app as Calendar (`Core/credentials.json`). Token: `Core/data/google_drive_token.json`. One-time consent: `bolt drive-auth`. Fail-soft if unauthenticated — local markdown still writes. |

**OAuth:** Drive/Docs Daily Log write is authorized locally (`Core/credentials.json` + `Core/data/google_drive_token.json`, both gitignored). Re-consent later with `bolt drive-auth` if the token is revoked. Calendar/Gmail still need their own tokens. Do not commit credentials or `*_token.json`.

If Drive is down or the token expires, briefing still writes local markdown and prints a one-line skip with the Daily Operations folder link. William can always edit the Drive docs in the browser; IDs stay in `Core/config.json`.
