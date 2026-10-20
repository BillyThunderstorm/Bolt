# Bolt sites (Cloudflare Pages + Worker)

Source for William's production sites, saved from what was live on Cloudflare
on 20 Oct 2026 (they had only ever lived in `/tmp/sites/...`). Cloudflare's
injected markup (email-obfuscation link, `__CF$cv$params` beacon) was stripped.

| Folder | Cloudflare project | URL |
|---|---|---|
| `bolt-fortress/` | Pages `bolt-fortress` | https://bolt.billythunderstorm.us |
| `billythunderstorm/` | Pages `billythunderstorm` | https://billythunderstorm.us |
| `billythunderstorm-live/` | Pages `billythunderstorm-live` | https://billythunderstorm.live |
| `bolt-api/` | Worker `bolt-api` | https://api.billythunderstorm.us |

Live data: `scripts/site_data_writer.py --push` (cron every 2 h) writes
`Data/site-data.json` (+ a root `site-data.json` mirror for the June Worker)
and pushes only those files to GitHub `main`. The Worker reads it from
raw.githubusercontent.com and serves `/api/status|queue|briefing|peaks|progress|health|all`.
The pages fetch those with `live-data.js`.

Deploy (needs `wrangler login` on Goddess, or a Cloudflare API token):

```bash
cd ~/developer/Bolt/Sites
wrangler deploy bolt-api/worker.js --name bolt-api --compatibility-date 2024-01-01
wrangler pages deploy bolt-fortress --project-name bolt-fortress --branch Hideout   # production branch is "Hideout"
wrangler pages deploy billythunderstorm --project-name billythunderstorm --branch Hub   # production branch is "Hub"
wrangler pages deploy billythunderstorm-live --project-name billythunderstorm-live --branch Outside   # production branch is "Outside"
```

After the Worker is redeployed (it reads `Data/site-data.json`), the root
mirror can be turned off with `BOLT_SITE_MIRROR_ROOT=0`.
