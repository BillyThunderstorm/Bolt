// Bolt API Worker (bolt-api) — serves Bolt's live site data to the Pages sites.
// Source of truth: Sites/bolt-api/worker.js in the Bolt repo.
// Data: Data/site-data.json on GitHub main, written by scripts/site_data_writer.py.
const SOURCES = [
  "https://raw.githubusercontent.com/BillyThunderstorm/Bolt/main/Data/site-data.json",
  "https://raw.githubusercontent.com/BillyThunderstorm/Bolt/main/site-data.json", // pre-July-2026 path
];
const CACHE_TTL = 30;
let cache = { data: null, ts: 0, source: null };

async function fetchSiteData() {
  const now = Date.now();
  if (cache.data && now - cache.ts < CACHE_TTL * 1000) return cache.data;
  for (const src of SOURCES) {
    try {
      const resp = await fetch(src, { headers: { "User-Agent": "BoltAPI/1.1" }, cf: { cacheTtl: 30 } });
      if (!resp.ok) continue;
      const data = await resp.json();
      cache = { data, ts: now, source: src };
      return data;
    } catch (e) {
      // try next source
    }
  }
  return cache.data || null;
}

const EMPTY_PROGRESS = { counts: { READY: 0, PARTIAL: 0, SHELL: 0, IDEA: 0 }, total: 0, percent_ready: 0, recent: [], updated: null };

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const headers = {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=30",
    };
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }
    const data = await fetchSiteData();
    const json = (obj, status = 200) => new Response(JSON.stringify(obj, null, 2), { status, headers });

    switch (path) {
      case "/api/status":
        return json(data?.status || { clips_made: 0, ready_to_post: 0, recordings_processed: 0, api_keys: { twitch: false, obs: false, discord: false, tiktok: false } });
      case "/api/queue":
        return json(data?.queue || []);
      case "/api/briefing":
        return json(data?.briefing || { date: new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "America/Chicago" }), action_items: [] });
      case "/api/peaks":
        return json(data?.peaks || []);
      case "/api/progress":
        return json(data?.progress || EMPTY_PROGRESS);
      case "/api/health":
        return json({ status: data ? "ok" : "no_data", timestamp: new Date().toISOString(), data_age: data?.generated_at || "unknown", source: cache.source });
      case "/api/all":
        return json(data ? { ...data, progress: data.progress || EMPTY_PROGRESS } : {});
      default:
        return json({ error: "Not found", endpoints: ["/api/status", "/api/queue", "/api/briefing", "/api/peaks", "/api/progress", "/api/health", "/api/all"] }, 404);
    }
  },
};
