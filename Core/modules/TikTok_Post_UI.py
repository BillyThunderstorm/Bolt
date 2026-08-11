#!/usr/bin/env python3
"""TikTok Post UI — compliant "Post to TikTok" page for audit demos.

Serves a local web UI that implements TikTok Content Sharing Guidelines:
  - creator_info (nickname, privacy options, interaction disables, max duration)
  - no default privacy; interactions off by default
  - commercial disclosure + branded-content privacy rules
  - music / branded consent text
  - publish only after explicit consent; status polling notice

Usage:
  bolt tiktok-post              # open UI (demo mode if no token)
  bolt tiktok-post --live       # require real token (no mock creator)
  bolt tiktok-post --port 8787

Environment:
  BOLT_TIKTOK_POST_DEMO=1       Force mock creator_info even if token exists
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

# Core/modules → repo root
_MODULE_DIR = Path(__file__).resolve().parent
_CORE_DIR = _MODULE_DIR.parent
_REPO_ROOT = _CORE_DIR.parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

try:
    from _paths import VERTICAL_CLIPS_DIR, DATA_DIR, REPO_ROOT
except Exception:
    REPO_ROOT = _REPO_ROOT
    VERTICAL_CLIPS_DIR = REPO_ROOT / "media" / "vertical_clips"
    DATA_DIR = REPO_ROOT / "Data"

READY_FILE = DATA_DIR / "ready_to_post.json"
DEFAULT_PORT = 8787

PRIVACY_LABELS = {
    "PUBLIC_TO_EVERYONE": "Everyone",
    "MUTUAL_FOLLOW_FRIENDS": "Friends",
    "FOLLOWER_OF_CREATOR": "Followers",
    "SELF_ONLY": "Only me",
}

# ── HTML (single page) ───────────────────────────────────────────────────────

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Bolt — Post to TikTok</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #171a21;
    --border: #2a3140;
    --text: #e8eaed;
    --muted: #9aa3b2;
    --accent: #25f4ee;
    --accent2: #fe2c55;
    --ok: #3ddc97;
    --warn: #f5c542;
    --err: #ff6b6b;
    --disabled: #3a4150;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh;
    font: 15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif;
    background: var(--bg); color: var(--text);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--border);
    background: #12151c;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 700; }
  header .badge {
    font-size: 12px; padding: 4px 8px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--muted);
  }
  header .badge.demo { color: var(--warn); border-color: #6a5520; }
  header .badge.live { color: var(--ok); border-color: #1e5c40; }
  main {
    max-width: 1100px; margin: 0 auto; padding: 20px;
    display: grid; grid-template-columns: 1.05fr 1fr; gap: 18px;
  }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  .card {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
  }
  .card h2 {
    margin: 0 0 12px; font-size: 13px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--muted);
  }
  .creator {
    display: flex; align-items: center; gap: 12px; margin-bottom: 14px;
  }
  .creator img, .avatar-fallback {
    width: 48px; height: 48px; border-radius: 50%;
    background: #222833; object-fit: cover;
  }
  .avatar-fallback {
    display: grid; place-items: center; font-weight: 700; color: var(--accent);
  }
  .creator .name { font-weight: 700; font-size: 16px; }
  .creator .handle { color: var(--muted); font-size: 13px; }
  label { display: block; font-size: 13px; color: var(--muted); margin: 10px 0 4px; }
  input[type=text], textarea, select {
    width: 100%; background: #0d1016; color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 12px; font: inherit;
  }
  select:invalid, select.placeholder { color: var(--muted); }
  textarea { min-height: 72px; resize: vertical; }
  .row { display: flex; flex-wrap: wrap; gap: 12px 18px; margin-top: 8px; }
  .check {
    display: flex; align-items: center; gap: 8px; font-size: 14px;
  }
  .check input:disabled + span { color: var(--disabled); }
  .hint {
    font-size: 12px; color: var(--muted); margin-top: 4px;
  }
  .prompt {
    display: none; margin-top: 8px; padding: 8px 10px;
    border-radius: 8px; background: #1c2433; border: 1px solid #334;
    font-size: 13px; color: var(--warn);
  }
  .prompt.show { display: block; }
  .consent {
    margin-top: 14px; padding: 12px; border-radius: 8px;
    background: #121722; border: 1px solid var(--border); font-size: 13px;
  }
  .consent a { color: var(--accent); }
  button#postBtn {
    width: 100%; margin-top: 14px; padding: 12px 16px;
    border: 0; border-radius: 10px; font: inherit; font-weight: 700;
    background: linear-gradient(90deg, var(--accent), #6ff); color: #041018;
    cursor: pointer;
  }
  button#postBtn:disabled {
    background: var(--disabled); color: #8a93a3; cursor: not-allowed;
  }
  .status {
    margin-top: 12px; padding: 10px 12px; border-radius: 8px;
    border: 1px solid var(--border); font-size: 13px; display: none;
  }
  .status.show { display: block; }
  .status.info { border-color: #2a4a5a; color: #b8e0f0; }
  .status.ok { border-color: #1e5c40; color: var(--ok); }
  .status.err { border-color: #6a2a2a; color: var(--err); }
  .clip-list { max-height: 280px; overflow: auto; }
  .clip {
    display: flex; justify-content: space-between; gap: 8px;
    padding: 8px 10px; border-radius: 8px; border: 1px solid transparent;
    cursor: pointer; margin-bottom: 4px;
  }
  .clip:hover { background: #1c2230; }
  .clip.selected { border-color: var(--accent); background: #152028; }
  .clip .meta { font-size: 12px; color: var(--muted); }
  video {
    width: 100%; max-height: 420px; border-radius: 10px;
    background: #000; margin-top: 8px;
  }
  .block-banner {
    display: none; margin-bottom: 12px; padding: 10px 12px;
    border-radius: 8px; background: #3a1a1a; border: 1px solid #6a2a2a;
    color: #ffb4b4; font-size: 13px;
  }
  .block-banner.show { display: block; }
  .req-tag {
    display: inline-block; font-size: 10px; padding: 1px 6px;
    border-radius: 4px; background: #222833; color: var(--muted);
    margin-left: 6px; vertical-align: middle;
  }
  footer {
    max-width: 1100px; margin: 0 auto 24px; padding: 0 20px;
    font-size: 12px; color: var(--muted);
  }
  code { font-size: 12px; background: #1a1f2a; padding: 1px 5px; border-radius: 4px; }
</style>
</head>
<body>
<header>
  <h1>Post to TikTok <span class="req-tag">Content Posting UX</span></h1>
  <div>
    <span id="modeBadge" class="badge">…</span>
  </div>
</header>
<main>
  <section class="card">
    <h2>1. Choose original clip</h2>
    <div id="clipList" class="clip-list"><p class="hint">Loading queue…</p></div>
    <video id="preview" controls playsinline></video>
    <p class="hint" id="clipPathHint"></p>
  </section>

  <section class="card">
    <h2>2. Export settings</h2>
    <div id="blockBanner" class="block-banner"></div>

    <div class="creator">
      <div id="avatarWrap"><div class="avatar-fallback" id="avatarFb">?</div></div>
      <div>
        <div class="name" id="creatorNick">Loading…</div>
        <div class="handle" id="creatorUser">@…</div>
      </div>
    </div>
    <p class="hint">Posting as this TikTok account (from creator_info). <span class="req-tag">1a</span></p>

    <label for="title">Title / caption <span class="req-tag">2a · 5b</span></label>
    <textarea id="title" maxlength="2200" placeholder="Edit before posting…"></textarea>

    <label for="privacy">Who can watch this video <span class="req-tag">2b no default</span></label>
    <select id="privacy" required>
      <option value="" selected disabled>Select privacy…</option>
    </select>
    <p class="hint" id="privacyHint">Options come from creator_info.privacy_level_options.</p>

    <label>Interaction ability <span class="req-tag">2c off by default</span></label>
    <div class="row">
      <label class="check"><input type="checkbox" id="allowComment" /><span>Allow Comment</span></label>
      <label class="check"><input type="checkbox" id="allowDuet" /><span>Allow Duet</span></label>
      <label class="check"><input type="checkbox" id="allowStitch" /><span>Allow Stitch</span></label>
    </div>

    <label class="check" style="margin-top:14px">
      <input type="checkbox" id="commercialOn" />
      <span>Disclose commercial content <span class="req-tag">3a off by default</span></span>
    </label>
    <div id="commercialBox" style="display:none; margin-left:8px; margin-top:8px">
      <label class="check"><input type="checkbox" id="yourBrand" /><span>Your brand</span></label>
      <label class="check" style="margin-top:6px"><input type="checkbox" id="brandedContent" /><span>Branded content</span></label>
      <div id="labelPrompt" class="prompt"></div>
      <p class="hint">If commercial disclosure is on, select at least one option. <span class="req-tag">3a</span></p>
    </div>

    <div class="consent">
      <label class="check">
        <input type="checkbox" id="consent" />
        <span id="consentText">By posting, you agree to TikTok's <a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener">Music Usage Confirmation</a>.</span>
      </label>
      <p class="hint" style="margin-top:8px">Publish only after you check this box. <span class="req-tag">5c</span></p>
    </div>

    <button id="postBtn" type="button" disabled>Post to TikTok</button>
    <div id="status" class="status"></div>
    <p class="hint" style="margin-top:10px">
      After you finish publishing, it may take a few minutes for the content to process and be visible on your profile.
      <span class="req-tag">5d</span>
    </p>
  </section>
</main>
<footer>
  Bolt Post UI · audit-oriented export screen ·
  printable worksheet: <code>Docs/guides/TIKTOK_AUDIT_DEMO_PRINTABLE.html</code>
</footer>

<script>
const state = {
  clips: [],
  selected: null,
  creator: null,
  mock: false,
  liveRequired: false,
};

const $ = (id) => document.getElementById(id);

function setStatus(kind, text) {
  const el = $("status");
  el.className = "status show " + kind;
  el.textContent = text;
}

function privacyLabel(code) {
  return ({
    PUBLIC_TO_EVERYONE: "Everyone",
    MUTUAL_FOLLOW_FRIENDS: "Friends",
    FOLLOWER_OF_CREATOR: "Followers",
    SELF_ONLY: "Only me",
  })[code] || code;
}

function updateConsentText() {
  const branded = $("commercialOn").checked && $("brandedContent").checked;
  const music = '<a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener">Music Usage Confirmation</a>';
  const bc = '<a href="https://www.tiktok.com/legal/page/global/bc-policy/en" target="_blank" rel="noopener">Branded Content Policy</a>';
  if (branded) {
    $("consentText").innerHTML = `By posting, you agree to TikTok's ${bc} and ${music}.`;
  } else {
    $("consentText").innerHTML = `By posting, you agree to TikTok's ${music}.`;
  }
}

function updateLabelPrompt() {
  const on = $("commercialOn").checked;
  const yours = $("yourBrand").checked;
  const branded = $("brandedContent").checked;
  const el = $("labelPrompt");
  if (!on) { el.classList.remove("show"); el.textContent = ""; return; }
  if (yours && branded) {
    el.textContent = "Your photo/video will be labeled as 'Paid partnership'.";
    el.classList.add("show");
  } else if (branded) {
    el.textContent = "Your photo/video will be labeled as 'Paid partnership'.";
    el.classList.add("show");
  } else if (yours) {
    el.textContent = "Your photo/video will be labeled as 'Promotional content'.";
    el.classList.add("show");
  } else {
    el.textContent = "You need to indicate if your content promotes yourself, a third party, or both.";
    el.classList.add("show");
  }
}

function applyBrandedPrivacyRules() {
  const branded = $("commercialOn").checked && $("brandedContent").checked;
  const sel = $("privacy");
  for (const opt of sel.options) {
    if (!opt.value) continue;
    if (opt.value === "SELF_ONLY") {
      opt.disabled = branded;
      opt.title = branded ? "Branded content visibility cannot be set to private." : "";
    }
  }
  if (branded && sel.value === "SELF_ONLY") {
    sel.value = "";
  }
  updateConsentText();
  updateLabelPrompt();
  updatePostEnabled();
}

function updatePostEnabled() {
  const hasClip = !!state.selected;
  const hasPrivacy = !!$("privacy").value;
  const consent = $("consent").checked;
  const commercial = $("commercialOn").checked;
  const brandOk = !commercial || $("yourBrand").checked || $("brandedContent").checked;
  const canPost = state.creator && state.creator.can_post !== false;
  const blocked = !canPost || !hasClip || !hasPrivacy || !consent || !brandOk;
  $("postBtn").disabled = blocked;
}

function renderClips() {
  const box = $("clipList");
  if (!state.clips.length) {
    box.innerHTML = "<p class='hint'>No postable clips found in the queue. Put finals in media/vertical_clips/ and run <code>bolt queue add …</code>.</p>";
    return;
  }
  box.innerHTML = "";
  state.clips.forEach((c, i) => {
    const div = document.createElement("div");
    div.className = "clip" + (state.selected && state.selected.id === c.id ? " selected" : "");
    div.innerHTML = `<div><strong>${escapeHtml(c.title || c.filename)}</strong><div class="meta">${escapeHtml(c.filename)} · ${c.status || ""} · score ${c.score ?? "—"}</div></div>`;
    div.onclick = () => selectClip(c);
    box.appendChild(div);
    if (i === 0 && !state.selected) selectClip(c);
  });
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, ch => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  })[ch]);
}

function selectClip(c) {
  state.selected = c;
  $("title").value = c.title || c.filename.replace(/\.[^.]+$/, "");
  $("preview").src = "/media/" + encodeURIComponent(c.filename);
  $("clipPathHint").textContent = c.path || c.filename;
  renderClips();
  updatePostEnabled();
}

function applyCreator(info) {
  state.creator = info;
  $("creatorNick").textContent = info.creator_nickname || "Unknown";
  $("creatorUser").textContent = "@" + (info.creator_username || "unknown");
  if (info.creator_avatar_url) {
    $("avatarWrap").innerHTML = `<img src="${info.creator_avatar_url}" alt="" />`;
  } else {
    const letter = (info.creator_nickname || "?").trim().charAt(0).toUpperCase();
    $("avatarWrap").innerHTML = `<div class="avatar-fallback">${letter}</div>`;
  }

  const sel = $("privacy");
  const current = sel.value;
  sel.innerHTML = `<option value="" selected disabled>Select privacy…</option>`;
  (info.privacy_level_options || []).forEach(code => {
    const opt = document.createElement("option");
    opt.value = code;
    opt.textContent = privacyLabel(code);
    sel.appendChild(opt);
  });
  // never restore a default — leave blank
  if (current && (info.privacy_level_options || []).includes(current)) {
    // only restore if user already chose; not a first-load default
  }
  sel.value = "";

  $("allowComment").checked = false;
  $("allowDuet").checked = false;
  $("allowStitch").checked = false;
  $("allowComment").disabled = !!info.comment_disabled;
  $("allowDuet").disabled = !!info.duet_disabled;
  $("allowStitch").disabled = !!info.stitch_disabled;

  if (info.can_post === false) {
    $("blockBanner").textContent = "You cannot post right now: " + (info.cannot_post_reason || "try again later");
    $("blockBanner").classList.add("show");
  } else {
    $("blockBanner").classList.remove("show");
  }

  $("privacyHint").textContent =
    "Max duration: " + (info.max_video_post_duration_sec || "?") + "s · options from creator_info";
  applyBrandedPrivacyRules();
  updatePostEnabled();
}

async function loadAll() {
  const qs = new URLSearchParams(location.search);
  state.liveRequired = qs.get("live") === "1";
  const cr = await fetch("/api/creator_info").then(r => r.json());
  if (!cr.success) {
    setStatus("err", "creator_info failed: " + (cr.error || "unknown"));
    $("modeBadge").textContent = "error";
    $("modeBadge").className = "badge";
    return;
  }
  state.mock = !!cr.mock;
  $("modeBadge").textContent = state.mock ? "DEMO (mock creator)" : "LIVE token";
  $("modeBadge").className = "badge " + (state.mock ? "demo" : "live");
  applyCreator(cr.data);

  const cl = await fetch("/api/clips").then(r => r.json());
  state.clips = cl.clips || [];
  renderClips();
}

$("commercialOn").addEventListener("change", () => {
  $("commercialBox").style.display = $("commercialOn").checked ? "block" : "none";
  if (!$("commercialOn").checked) {
    $("yourBrand").checked = false;
    $("brandedContent").checked = false;
  }
  applyBrandedPrivacyRules();
});
$("yourBrand").addEventListener("change", applyBrandedPrivacyRules);
$("brandedContent").addEventListener("change", applyBrandedPrivacyRules);
$("privacy").addEventListener("change", updatePostEnabled);
$("consent").addEventListener("change", updatePostEnabled);
$("title").addEventListener("input", updatePostEnabled);

// Hover-style title for Only me when branded (guideline 3b)
$("privacy").addEventListener("mouseover", (e) => {
  const branded = $("commercialOn").checked && $("brandedContent").checked;
  if (branded) {
    $("privacy").title = "Branded content visibility cannot be set to private.";
  } else {
    $("privacy").title = "";
  }
});

$("postBtn").addEventListener("click", async () => {
  if (!state.selected) return;
  updatePostEnabled();
  if ($("postBtn").disabled) return;

  const payload = {
    clip_id: state.selected.id,
    filename: state.selected.filename,
    path: state.selected.path,
    title: $("title").value.trim(),
    privacy: $("privacy").value,
    allow_comment: $("allowComment").checked,
    allow_duet: $("allowDuet").checked,
    allow_stitch: $("allowStitch").checked,
    commercial_on: $("commercialOn").checked,
    your_brand: $("yourBrand").checked,
    branded_content: $("brandedContent").checked,
    consent: $("consent").checked,
    demo: state.mock,
  };

  setStatus("info", "Sending to TikTok… After publishing, processing may take a few minutes.");
  $("postBtn").disabled = true;
  try {
    const res = await fetch("/api/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      setStatus("ok", "Published" + (data.url ? ": " + data.url : "") +
        (data.publish_id ? " (publish_id " + data.publish_id + ")" : "") +
        (data.demo ? " [demo dry-run — no API call]" : ""));
    } else {
      setStatus("err", "Publish failed: " + (data.error || "unknown"));
      updatePostEnabled();
    }
  } catch (err) {
    setStatus("err", "Request error: " + err);
    updatePostEnabled();
  }
});

loadAll();
</script>
</body>
</html>
"""


def _load_queue_clips() -> list[dict]:
    """Postable clips from ready_to_post.json that still have files."""
    clips: list[dict] = []
    if READY_FILE.exists():
        try:
            data = json.loads(READY_FILE.read_text(encoding="utf-8"))
            raw = data.get("clips") if isinstance(data, dict) else data
            for c in raw or []:
                if not isinstance(c, dict):
                    continue
                if c.get("status") not in (None, "ready", "approved", "held"):
                    # still allow held hand-edits so Blasted etc. appear
                    if c.get("status") != "held":
                        continue
                path = Path(str(c.get("clip_path") or ""))
                if not path.is_file():
                    # try vertical dir by name
                    name = path.name
                    alt = VERTICAL_CLIPS_DIR / name
                    if alt.is_file():
                        path = alt
                    else:
                        continue
                clips.append(
                    {
                        "id": c.get("id") or path.stem,
                        "filename": path.name,
                        "path": str(path.resolve()),
                        "title": c.get("title") or path.stem,
                        "score": c.get("score"),
                        "status": c.get("status") or "ready",
                    }
                )
        except Exception:
            pass

    # Also list hand files in vertical_clips not already included
    seen = {c["filename"] for c in clips}
    if VERTICAL_CLIPS_DIR.is_dir():
        for p in sorted(VERTICAL_CLIPS_DIR.iterdir()):
            if p.suffix.lower() not in {".mp4", ".mov", ".webm"}:
                continue
            if p.name in seen:
                continue
            clips.append(
                {
                    "id": f"file:{p.name}",
                    "filename": p.name,
                    "path": str(p.resolve()),
                    "title": p.stem,
                    "score": None,
                    "status": "file",
                }
            )
    return clips


def _resolve_safe_media(filename: str) -> Optional[Path]:
    name = Path(filename).name  # strip any path
    candidate = (VERTICAL_CLIPS_DIR / name).resolve()
    try:
        candidate.relative_to(VERTICAL_CLIPS_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _mark_queue_posted(clip_id: str, share_url: Optional[str] = None) -> None:
    if not READY_FILE.exists() or not clip_id or clip_id.startswith("file:"):
        return
    try:
        data = json.loads(READY_FILE.read_text(encoding="utf-8"))
        clips = data.get("clips") if isinstance(data, dict) else data
        from datetime import datetime, timezone

        now = datetime.now().astimezone().isoformat()
        for c in clips or []:
            if str(c.get("id")) != str(clip_id):
                continue
            c["status"] = "posted"
            c["posted_at"] = now
            if share_url:
                c["share_url"] = share_url
            plan = c.get("auto_post") or {}
            plan["status"] = "posted"
            c["auto_post"] = plan
            break
        if isinstance(data, dict):
            READY_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def create_app(*, force_demo: bool = False, live_required: bool = False):
    from flask import Flask, jsonify, request, Response, send_file

    app = Flask(__name__)
    app.config["FORCE_DEMO"] = force_demo
    app.config["LIVE_REQUIRED"] = live_required

    @app.get("/")
    def index():
        return Response(PAGE_HTML, mimetype="text/html")

    @app.get("/api/creator_info")
    def api_creator_info():
        from modules.TikTok_Publisher import TikTokPublisher

        allow_mock = (not app.config["LIVE_REQUIRED"]) or app.config["FORCE_DEMO"]
        if app.config["FORCE_DEMO"]:
            # still construct publisher; force mock path
            pub = TikTokPublisher(access_token="")
            return jsonify(pub.query_creator_info(allow_mock=True))
        pub = TikTokPublisher()
        return jsonify(pub.query_creator_info(allow_mock=allow_mock))

    @app.get("/api/clips")
    def api_clips():
        return jsonify({"clips": _load_queue_clips()})

    @app.get("/media/<path:filename>")
    def media(filename: str):
        path = _resolve_safe_media(filename)
        if not path:
            return jsonify({"error": "not found"}), 404
        mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
        return send_file(path, mimetype=mime, conditional=True)

    @app.post("/api/publish")
    def api_publish():
        body = request.get_json(force=True, silent=True) or {}
        if not body.get("consent"):
            return jsonify({"success": False, "error": "consent required"}), 400
        privacy = (body.get("privacy") or "").strip()
        if not privacy:
            return jsonify({"success": False, "error": "privacy must be selected"}), 400

        commercial = bool(body.get("commercial_on"))
        your_brand = bool(body.get("your_brand"))
        branded = bool(body.get("branded_content"))
        if commercial and not (your_brand or branded):
            return jsonify(
                {
                    "success": False,
                    "error": "select Your brand and/or Branded content",
                }
            ), 400
        if branded and privacy == "SELF_ONLY":
            return jsonify(
                {
                    "success": False,
                    "error": "Branded content visibility cannot be set to private.",
                }
            ), 400

        filename = body.get("filename") or ""
        path = _resolve_safe_media(filename)
        if not path and body.get("path"):
            # only allow if under vertical_clips
            try:
                p = Path(body["path"]).resolve()
                p.relative_to(VERTICAL_CLIPS_DIR.resolve())
                if p.is_file():
                    path = p
            except Exception:
                path = None
        if not path:
            return jsonify({"success": False, "error": "clip file not found"}), 404

        title = (body.get("title") or path.stem).strip()[:2200]
        disable_comment = not bool(body.get("allow_comment"))
        disable_duet = not bool(body.get("allow_duet"))
        disable_stitch = not bool(body.get("allow_stitch"))

        # Demo dry-run: validate UX only
        if app.config["FORCE_DEMO"] or body.get("demo"):
            if not app.config["LIVE_REQUIRED"]:
                return jsonify(
                    {
                        "success": True,
                        "demo": True,
                        "publish_id": "demo_dry_run",
                        "url": None,
                        "message": "Demo dry-run: UX validated; no TikTok API call.",
                    }
                )

        from modules.TikTok_Publisher import TikTokPublisher

        pub = TikTokPublisher()
        # Re-check creator can post
        info = pub.query_creator_info(allow_mock=False)
        if info.get("success") and info.get("data", {}).get("can_post") is False:
            return jsonify(
                {
                    "success": False,
                    "error": info["data"].get("cannot_post_reason")
                    or "creator cannot post right now",
                }
            ), 400

        result = pub.publish(
            str(path),
            title,
            privacy=privacy,
            disable_comment=disable_comment,
            disable_duet=disable_duet,
            disable_stitch=disable_stitch,
            brand_content_toggle=branded,
            brand_organic_toggle=your_brand,
        )
        if result.get("success"):
            _mark_queue_posted(str(body.get("clip_id") or ""), result.get("url"))
        return jsonify(result)

    @app.get("/api/status/<publish_id>")
    def api_status(publish_id: str):
        from modules.TikTok_Publisher import TikTokPublisher, TIKTOK_STATUS_URL
        import requests

        pub = TikTokPublisher()
        if not pub.token:
            return jsonify({"success": False, "error": "no token"}), 400
        try:
            resp = requests.post(
                TIKTOK_STATUS_URL,
                headers=pub._headers,
                json={"publish_id": publish_id},
                timeout=15,
            )
            return jsonify(resp.json())
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    return app


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bolt Post-to-TikTok UI (audit-compliant export screen)"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default 127.0.0.1 — local only)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Force mock creator_info (safe for filming without a token)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Require real TikTok token (no mock fallback)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser tab",
    )
    args = parser.parse_args(argv)

    force_demo = args.demo or os.getenv("BOLT_TIKTOK_POST_DEMO", "").strip() in {
        "1",
        "true",
        "yes",
    }
    app = create_app(force_demo=force_demo, live_required=args.live)

    url = f"http://{args.host}:{args.port}/"
    if args.live:
        url += "?live=1"

    print()
    print("  Bolt — Post to TikTok UI")
    print(f"  → {url}")
    if force_demo:
        print("  Mode: DEMO (mock creator_info; publish is dry-run)")
    elif args.live:
        print("  Mode: LIVE (token required; real publish)")
    else:
        print("  Mode: auto (live creator if token works, else demo mock)")
    print("  Printable audit worksheet:")
    print("    Docs/guides/TIKTOK_AUDIT_DEMO_PRINTABLE.html")
    print("  Ctrl+C to stop.")
    print()

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # Flask reloader confuses CLI; disable it.
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
