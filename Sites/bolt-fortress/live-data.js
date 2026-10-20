// Bolt Sites — Live Data Fetcher
// In production: fetches from Cloudflare Worker API
// In development: fetches from localhost:8103
const API_BASE = window.BOLT_API_URL || 
  (window.location.hostname === 'localhost' ? 'http://localhost:8103' : 'https://api.billythunderstorm.us');

async function fetchJSON(endpoint) {
  try {
    const resp = await fetch(`${API_BASE}${endpoint}`, { cache: 'no-store' });
    if (!resp.ok) return null;
    return await resp.json();
  } catch (e) {
    console.warn(`Bolt API unavailable (${endpoint}):`, e.message);
    return null;
  }
}

async function loadStatus() {
  const data = await fetchJSON('/api/status');
  if (!data) return;

  const el = (id) => document.getElementById(id);
  if (el('sClips')) el('sClips').textContent = data.ready_to_post ?? 0;
  if (el('sPosted')) el('sPosted').textContent = data.clips_made ?? 0;
  if (el('sAvg')) el('sAvg').textContent = data.avg_score ?? '—';

  const badge = document.getElementById('queueBadge');
  if (badge && data.ready_to_post !== undefined) {
    badge.textContent = `${data.ready_to_post} ready`;
  }

  if (data.peak_hours && data.peak_hours.length) {
    updatePeaksFromData(data.peak_hours);
  }
}

async function loadQueue() {
  const data = await fetchJSON('/api/queue');
  if (!data || !data.length) return;

  const list = document.getElementById('clipList');
  if (!list) return;

  list.innerHTML = data.map(clip => {
    const score = clip.score || '—';
    const scoreClass = typeof score === 'number' ? (score >= 80 ? 's-high' : score >= 65 ? 's-mid' : 's-high') : 's-high';
    const tagClass = clip.status === 'posted' || clip.status === 'manual_upload_ready' ? (clip.status === 'posted' ? 'tag-posted' : 'tag-queue') : 'tag-mid';
    const tagLabel = clip.status === 'posted' ? 'posted' : clip.status === 'manual_upload_ready' ? 'queue' : 'mid';
    return `
      <div class="clip">
        <div class="clip-score ${scoreClass}">${score}</div>
        <div class="clip-info">
          <div class="clip-name">${clip.title || 'Untitled clip'}</div>
          <div class="clip-meta">${clip.platforms || '?'} platforms · ${clip.status || 'queued'}</div>
        </div>
        <span class="clip-tag ${tagClass}">${tagLabel}</span>
      </div>`;
  }).join('');
}

async function loadBriefing() {
  const data = await fetchJSON('/api/briefing');
  if (!data) return;

  const dateEl = document.querySelector('.brief-date');
  if (dateEl && data.date) dateEl.textContent = data.date;

  const itemsEl = document.querySelector('.brief-items');
  if (itemsEl && data.action_items && data.action_items.length) {
    itemsEl.innerHTML = data.action_items.map((item, i) =>
      `<div class="brief-item"><span class="brief-num">${i + 1}</span><span class="brief-text">${item}</span></div>`
    ).join('');
  }
}

async function loadPeaks() {
  const data = await fetchJSON('/api/peaks');
  if (!data) return;
  updatePeaksFromData(data);
}

function updatePeaksFromData(peaks) {
  const ids = ['pMorning', 'pLunch', 'pPrime'];
  const now = new Date().getHours();
  peaks.forEach((peak, i) => {
    const id = ids[i];
    if (!id) return;
    const el = document.getElementById(id);
    const row = el?.closest('.peak-row');
    if (!el || !row) return;

    // site-data.json is written every ~2h, so its "active" flag goes stale;
    // compute from the hours in Central time instead.
    const ctHour = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'America/Chicago' }).format(new Date()));
    const h = Number.isFinite(ctHour) ? ctHour : now;
    const active = peak.start_hour <= h && h < peak.end_hour;
    el.textContent = active ? 'live now' : h < peak.start_hour ? 'upcoming' : 'done';
    el.className = `peak-status ${active ? 'now' : 'later'}`;
    row.classList.toggle('active', active);
  });
}

// ── Bolt progress cloud ──
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function loadProgress() {
  const box = document.getElementById('progressCloud');
  if (!box) return;
  let p = await fetchJSON('/api/progress');
  let src = 'live';
  if (!p || !p.counts || !p.total) {
    const all = await fetchJSON('/api/all');
    p = all && all.progress;
  }
  if (!p || !p.counts || !p.total) {
    // Keep the snapshot baked into the page.
    const s = document.getElementById('cpSrc');
    if (s) s.textContent = 'snapshot';
    return;
  }
  const c = p.counts;
  const total = p.total || 1;
  const pct = p.percent_ready ?? Math.round((100 * (c.READY || 0)) / total);
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('cpPct', `${pct}%`);
  set('cpReady', c.READY ?? 0);
  set('cpPartial', c.PARTIAL ?? 0);
  set('cpShell', c.SHELL ?? 0);
  set('cpIdea', c.IDEA ?? 0);
  set('cpSrc', src);
  const bar = document.getElementById('cpBar');
  if (bar) {
    const w = k => `${((100 * (c[k] || 0)) / total).toFixed(1)}%`;
    bar.innerHTML = ['READY', 'PARTIAL', 'SHELL', 'IDEA']
      .map(k => `<span class="lv-${k.toLowerCase()}" style="width:${w(k)}"></span>`).join('');
    bar.setAttribute('aria-label', `${c.READY || 0} ready, ${c.PARTIAL || 0} partial, ${c.SHELL || 0} shell, ${c.IDEA || 0} idea`);
  }
  const list = document.getElementById('cpRecent');
  if (list && Array.isArray(p.recent) && p.recent.length) {
    list.innerHTML = p.recent.slice(0, 4).map(r => {
      const name = String(r.name || '').replace(/\s*\(.*\)\s*$/, '') || r.name;
      const day = (r.display || r.date || '').split(',')[0];
      return `<li><span class="cp-dot lv-ready"></span><span class="n">${esc(name)}</span><span class="d">${esc(day)}</span></li>`;
    }).join('');
  }
  if (p.updated) set('cpUpdated', `updated ${String(p.updated).replace(/^~/, '')}`);
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadQueue(), loadBriefing(), loadPeaks(), loadProgress()]);
}
refreshAll();
setInterval(refreshAll, 60000);
