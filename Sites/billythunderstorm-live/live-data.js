// Bolt Sites — Live Status Fetcher
const API_BASE = window.BOLT_API_URL ||
  (window.location.hostname === 'localhost' ? 'http://localhost:8103' : 'https://api.billythunderstorm.us');

async function fetchJSON(endpoint) {
  try {
    const resp = await fetch(`${API_BASE}${endpoint}`, { cache: 'no-store' });
    if (!resp.ok) return null;
    return await resp.json();
  } catch (e) {
    console.warn('Bolt API unavailable:', e.message);
    return null;
  }
}

async function updateLiveStatus() {
  const status = await fetchJSON('/api/status');
  const peaks = await fetchJSON('/api/peaks');

  if (!status) return;

  const indicator = document.getElementById('liveIndicator');
  const text = document.getElementById('liveText');
  const msg = document.getElementById('statusMessage');
  const streamStatus = document.getElementById('streamStatus');

  let isLive = false;
  if (peaks) {
    isLive = peaks.some(p => p.active);
  }

  if (isLive) {
    indicator.className = 'live-indicator live';
    text.textContent = 'LIVE';
    msg.textContent = 'Billy is streaming right now! Come watch.';
    streamStatus.textContent = 'Live Now';
    streamStatus.style.color = 'var(--red)';
  }
}

updateLiveStatus();
setInterval(updateLiveStatus, 60000);
