       # Bolt Upgrade Status

Source of truth: `/Users/carter/developer/Bolt`

## Week 1: LLM Titles

- [x] Copy code from `UPGRADE_CODE_EXAMPLES.md`
- [x] Update `modules/Title_Generator.py`
- [x] Test with 10 clips
- [x] Enable in production
- [x] Monitor results

## What Changed

- `modules/Title_Generator.py` supports AI title generation when enabled, caches responses, cleans hashtags, and falls back to templates.
- `config.json` has `quality_tiers.use_ai_titles` enabled.
- `scripts/test_title_upgrade_10_clips.py` validates 10 representative clip scenarios without spending API credits.
- `scripts/monitor_title_results.py` gives a quick readiness/results summary.

## Commands

```bash
python3 -m unittest tests.test_title_generator tests.test_multi_publisher tests.test_log_clip_performance
python3 scripts/test_title_upgrade_10_clips.py
python3 scripts/monitor_title_results.py
python3 scripts/log_clip_performance.py --list
```

## Production Note

AI titles are enabled in config, but live AI calls still require a real
`OPENAI_API_KEY`. If the key is missing or still set to the placeholder, Bolt
keeps working through the local template fallback.

## Next: Auto-Posting With Safeguards

- [x] Add 30-minute pre-peak review window
- [x] Auto-post when approved or when the review deadline is missed
- [x] Hold rejected clips and record the rejection reason
- [x] Add Twitch chat overrides: `!postnow`, `!dontpost`, `!stopclip`
- [x] Keep failed publish attempts in the queue for manual posting or retry

Real publishing uses `modules/TikTok_Publisher.py` and requires
`TIKTOK_ACCESS_TOKEN`. Without that token, the queue/review/override flow still
works, and failed publish attempts stay visible instead of disappearing.

## Producer Commands From Twitch Chat

- [x] `!postnow [clip_id]` publishes the next ready clip immediately
- [x] `!dontpost [clip_id] <reason>` holds a clip and records why
- [x] `!stopclip [clip_id] <reason>` emergency-holds a clip
- [x] `!skip [clip_id] <reason>` alias for holding a clip
- [x] `!rank <score>` or `!rank <clip_id> <score>` overrides queue score/tier
- [x] `!config <safe_key> <value>` allows guarded live tuning for selected config keys

## TikTok Token Setup

- [x] Add `scripts/get_tiktok_token.py` guided OAuth helper
- [x] Save TikTok client credentials, access token, refresh token, scope, and expiry values to `.env`
- [x] Add `modules/TikTok_Auth.py` for refreshable token management
- [x] Teach `modules/TikTok_Publisher.py` to refresh the access token before publishing

Direct auto-posting still depends on TikTok approving the app for `video.publish`.
The helper can request the scope, but TikTok decides whether it is granted.
