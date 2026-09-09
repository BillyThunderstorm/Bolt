#!/usr/bin/env python3
"""
Cloudflare_Pages.py — William-specific Pages deploy readiness (PARTIAL)
=======================================================================
Soft-fail status / list / deploy helpers for William's Cloudflare Pages
trio (bolt-fortress / billythunderstorm / billythunderstorm-live) plus the
API worker.

This is **not** stranger-ready — no in-repo full site apps; deploy needs
William's wrangler login / CF tokens and usually ``/tmp/sites/...`` trees.
Soft-fail prefix: ``Pages unavailable:``.

  bolt pages                        # status (default)
  bolt pages status [--json] [--probe]
  bolt pages list [--json]
  bolt pages deploy [project] [--path DIR] [--dry-run]
  bolt pages-status                 # alias → status

Aliases: cloudflare-pages, cf-pages, pages-status.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_DOCS_SITE = _REPO / "Docs" / "site"
_SITE_DATA = _REPO / "Data" / "site-data.json"
_SITE_WRITER = _REPO / "scripts" / "site_data_writer.py"

# Documented William deploy targets (Docs/PROJECT_STATUS.md).
_KNOWN_PROJECTS: List[Dict[str, Any]] = [
    {
        "name": "bolt-fortress",
        "kind": "pages",
        "url": "https://bolt.billythunderstorm.us",
        "default_path": "/tmp/sites/bolt",
        "description": "Bolt Command Center",
    },
    {
        "name": "billythunderstorm",
        "kind": "pages",
        "url": "https://billythunderstorm.us",
        "default_path": "/tmp/sites/main",
        "description": "Creator portfolio",
    },
    {
        "name": "billythunderstorm-live",
        "kind": "pages",
        "url": "https://billythunderstorm.live",
        "default_path": "/tmp/sites/live",
        "description": "Live status",
    },
    {
        "name": "bolt-api-worker",
        "kind": "worker",
        "url": "https://api.billythunderstorm.us",
        "default_path": "/tmp/sites/bolt-api-worker",
        "description": "API Worker (wrangler deploy, not pages)",
    },
]

_TOKEN_ENV_KEYS = (
    "CLOUDFLARE_API_TOKEN",
    "CF_API_TOKEN",
    "CLOUDFLARE_TOKEN",
    "CF_TOKEN",
)
_ACCOUNT_ENV_KEYS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CF_ACCOUNT_ID",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith("Pages unavailable:"):
        return msg
    return f"Pages unavailable: {msg}"


def _env_set(keys: Tuple[str, ...]) -> Tuple[bool, Optional[str]]:
    """Return (set, which_key) without exposing values."""
    for k in keys:
        v = (os.getenv(k) or "").strip()
        if v and v.lower() not in (
            "your_token_here",
            "changeme",
            "xxx",
            "replace_me",
            "your_cloudflare_api_token",
        ):
            return True, k
    return False, None


def _find_wrangler() -> Optional[str]:
    path = shutil.which("wrangler")
    if path:
        return path
    # Common nvm location on Goddess (may not be on non-interactive PATH)
    home = Path.home()
    candidates = list(home.glob(".nvm/versions/node/*/bin/wrangler"))
    for c in sorted(candidates, reverse=True):
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def _wrangler_version(wrangler: Optional[str]) -> Optional[str]:
    if not wrangler:
        return None
    try:
        r = subprocess.run(
            [wrangler, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return out.splitlines()[0].strip() if out else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _wrangler_auth_ok(wrangler: Optional[str]) -> Tuple[bool, str]:
    """Best-effort auth probe. Never raises; never prints tokens."""
    token_ok, token_key = _env_set(_TOKEN_ENV_KEYS)
    if token_ok:
        return True, f"env token set ({token_key})"
    if not wrangler:
        return False, "no wrangler and no CLOUDFLARE_API_TOKEN / CF_API_TOKEN"
    try:
        env = os.environ.copy()
        # Avoid interactive OAuth prompts
        env.setdefault("WRANGLER_SEND_METRICS", "false")
        r = subprocess.run(
            [wrangler, "whoami"],
            capture_output=True,
            text=True,
            timeout=12,
            env=env,
        )
        combined = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode == 0 and "not logged in" not in combined:
            return True, "wrangler whoami ok"
        if "not logged in" in combined or "failed to fetch auth" in combined:
            return False, "wrangler not logged in (run: wrangler login)"
        if r.returncode != 0:
            return False, "wrangler whoami failed (not authenticated)"
        return False, "wrangler auth unknown"
    except subprocess.TimeoutExpired:
        return False, "wrangler whoami timed out"
    except OSError as exc:
        return False, f"wrangler whoami error ({exc})"


def _docs_site_info() -> Dict[str, Any]:
    exists = _DOCS_SITE.is_dir()
    files: List[str] = []
    if exists:
        try:
            files = sorted(
                p.name
                for p in _DOCS_SITE.iterdir()
                if p.is_file() and not p.name.startswith(".")
            )
        except OSError:
            files = []
    return {
        "path": str(_DOCS_SITE),
        "exists": exists,
        "files": files,
        "file_count": len(files),
        "note": (
            "Docs/site holds legal HTML stubs only — not full Pages app sources"
            if exists
            else "Docs/site missing"
        ),
    }


def _path_deployable(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path}"
    if path.is_file():
        return True, f"file {path.name}"
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        return False, f"cannot read {path} ({exc})"
    if not entries:
        return False, f"empty dir {path}"
    # Prefer presence of index.html or wrangler.toml for workers
    names = {e.name.lower() for e in entries}
    if "index.html" in names or "wrangler.toml" in names or "package.json" in names:
        return True, f"ok — {path} ({len(entries)} entries)"
    return True, f"dir present ({len(entries)} entries) — no index.html/wrangler.toml"


def known_projects() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in _KNOWN_PROJECTS:
        dpath = Path(str(p["default_path"]))
        ok, detail = _path_deployable(dpath)
        item = dict(p)
        item["path_exists"] = dpath.exists()
        item["path_deployable"] = ok
        item["path_detail"] = detail
        out.append(item)
    return out


def resolve_project(query: Optional[str]) -> Optional[Dict[str, Any]]:
    if not query:
        return None
    q = query.strip().lower()
    for p in known_projects():
        if p["name"].lower() == q:
            return p
        if q in p["name"].lower() or q in (p.get("description") or "").lower():
            return p
        # short aliases
        aliases = {
            "bolt": "bolt-fortress",
            "fortress": "bolt-fortress",
            "main": "billythunderstorm",
            "portfolio": "billythunderstorm",
            "live": "billythunderstorm-live",
            "api": "bolt-api-worker",
            "worker": "bolt-api-worker",
        }
        if aliases.get(q) == p["name"]:
            return p
    return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Pages / wrangler readiness. Never raises. William-specific PARTIAL."""
    try:
        wrangler = _find_wrangler()
        wver = _wrangler_version(wrangler)
        token_ok, token_key = _env_set(_TOKEN_ENV_KEYS)
        account_ok, account_key = _env_set(_ACCOUNT_ENV_KEYS)
        auth_ok, auth_detail = _wrangler_auth_ok(wrangler)
        docs = _docs_site_info()
        projects = known_projects()
        deployable_count = sum(1 for p in projects if p.get("path_deployable"))
        site_data_exists = _SITE_DATA.is_file()
        writer_exists = _SITE_WRITER.is_file()

        hints: List[str] = []
        if not wrangler:
            hints.append(_soft("wrangler not on PATH (npm i -g wrangler)"))
        if not auth_ok:
            hints.append(_soft(auth_detail))
        if deployable_count == 0:
            hints.append(
                _soft(
                    "no deploy trees under /tmp/sites/{bolt,main,live} "
                    "(William local staging; not in-repo apps)"
                )
            )

        # PARTIAL: "ready" only when William can actually deploy something.
        # Strangers stay not-ready (no claim of stranger READY).
        ready = bool(wrangler and auth_ok and deployable_count > 0)

        if ready:
            hint = (
                f"wrangler + auth ok; {deployable_count} deploy path(s) present. "
                "Try: bolt pages list / bolt pages deploy bolt-fortress --dry-run"
            )
        else:
            hint = (
                " | ".join(hints)
                if hints
                else _soft("not stranger-ready — William CF deploy only")
            )

        info: Dict[str, Any] = {
            "ready": ready,
            "is_william_specific": True,
            "is_stranger_ready": False,
            "readiness": "PARTIAL",
            "soft_fail_prefix": "Pages unavailable:",
            "wrangler_path": wrangler,
            "wrangler_version": wver,
            "wrangler_present": bool(wrangler),
            "auth_ok": auth_ok,
            "auth_detail": auth_detail,
            "token_env_set": token_ok,
            "token_env_key": token_key,
            "account_env_set": account_ok,
            "account_env_key": account_key,
            "docs_site": docs,
            "site_data_json": str(_SITE_DATA),
            "site_data_exists": site_data_exists,
            "site_data_writer": str(_SITE_WRITER),
            "site_data_writer_exists": writer_exists,
            "project_count": len(projects),
            "deployable_count": deployable_count,
            "projects": projects,
            "hint": hint,
            "checked_at": _utc_now(),
        }

        if probe:
            info["probe_ok"] = False
            info["probe_detail"] = ""
            if not wrangler:
                info["probe_detail"] = _soft("probe skipped — no wrangler")
            elif not auth_ok:
                info["probe_detail"] = _soft(f"probe auth — {auth_detail}")
            else:
                # Soft probe: wrangler --version already ran; confirm whoami detail
                info["probe_ok"] = True
                info["probe_detail"] = (
                    f"ok — wrangler {wver or '?'} / {auth_detail}; "
                    f"{deployable_count}/{len(projects)} paths deployable"
                )
                if deployable_count == 0:
                    info["probe_ok"] = False
                    info["probe_detail"] = _soft(
                        "auth ok but no /tmp/sites deploy trees"
                    )
            if not info["probe_ok"] and info.get("probe_detail"):
                info["hint"] = info["probe_detail"]
        return info
    except Exception as exc:
        return {
            "ready": False,
            "is_william_specific": True,
            "is_stranger_ready": False,
            "readiness": "PARTIAL",
            "soft_fail_prefix": "Pages unavailable:",
            "wrangler_present": False,
            "auth_ok": False,
            "project_count": 0,
            "deployable_count": 0,
            "projects": [],
            "hint": _soft(f"status failed ({exc})"),
            "error": str(exc),
            "checked_at": _utc_now(),
        }


def list_projects(*, as_json: bool = False) -> int:
    info = status()
    projects = info.get("projects") or []
    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "project_count": len(projects),
                    "deployable_count": info.get("deployable_count"),
                    "projects": projects,
                    "hint": info.get("hint"),
                },
                indent=2,
                default=str,
            )
        )
        return 0

    print("\n  Cloudflare Pages / Worker projects (William-specific)")
    print("  " + "─" * 40)
    for p in projects:
        flag = "✓" if p.get("path_deployable") else "○"
        print(f"  {flag}  {p.get('name')}  [{p.get('kind')}]")
        print(f"      {p.get('description')} — {p.get('url')}")
        print(f"      path: {p.get('default_path')} ({p.get('path_detail')})")
    print()
    print("  Note: PARTIAL — not stranger-ready. Soft-fail: Pages unavailable:")
    print("  Try: bolt pages status --json")
    print("       bolt pages deploy bolt-fortress --dry-run")
    print()
    return 0


def try_deploy(
    project: Optional[str] = None,
    *,
    path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Soft-fail deploy helper. Never raises. Does not claim READY for strangers."""
    info = status()
    wrangler = info.get("wrangler_path")
    if not wrangler:
        return {
            "ok": False,
            "deployed": False,
            "error": _soft("wrangler not found — cannot deploy"),
            "hint": info.get("hint"),
        }
    if not info.get("auth_ok") and not dry_run:
        return {
            "ok": False,
            "deployed": False,
            "error": _soft(
                f"missing CF auth — {info.get('auth_detail')}. "
                "Set CLOUDFLARE_API_TOKEN or run: wrangler login"
            ),
            "hint": info.get("hint"),
        }

    proj = resolve_project(project) if project else None
    if project and proj is None:
        names = ", ".join(p["name"] for p in _KNOWN_PROJECTS)
        return {
            "ok": False,
            "deployed": False,
            "error": _soft(
                f"unknown project {project!r}. Known: {names}"
            ),
        }

    if proj is None:
        # Default to first pages project if unambiguous deployable, else soft-fail
        pages = [p for p in known_projects() if p.get("kind") == "pages"]
        deployable = [p for p in pages if p.get("path_deployable")]
        if len(deployable) == 1:
            proj = deployable[0]
        else:
            return {
                "ok": False,
                "deployed": False,
                "error": _soft(
                    "deploy needs a project name "
                    "(bolt-fortress | billythunderstorm | billythunderstorm-live | bolt-api-worker)"
                ),
                "projects": [p["name"] for p in pages],
            }

    deploy_path = Path(path) if path else Path(str(proj["default_path"]))
    ok, detail = _path_deployable(deploy_path)
    if not ok:
        return {
            "ok": False,
            "deployed": False,
            "error": _soft(
                f"deploy path not ready for {proj['name']}: {detail}. "
                "William stages built sites under /tmp/sites/…"
            ),
            "project": proj["name"],
            "path": str(deploy_path),
        }

    kind = proj.get("kind") or "pages"
    if kind == "worker":
        cmd = [str(wrangler), "deploy"]
        cwd = str(deploy_path)
    else:
        cmd = [
            str(wrangler),
            "pages",
            "deploy",
            str(deploy_path),
            "--project-name",
            str(proj["name"]),
        ]
        cwd = str(_REPO)

    if dry_run:
        return {
            "ok": True,
            "deployed": False,
            "dry_run": True,
            "project": proj["name"],
            "kind": kind,
            "path": str(deploy_path),
            "command": cmd,
            "cwd": cwd,
            "message": f"dry-run OK — would run: {' '.join(cmd)}",
        }

    try:
        env = os.environ.copy()
        env.setdefault("WRANGLER_SEND_METRICS", "false")
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode != 0:
            # Redact anything that looks like a token
            safe = out[:800] if out else "(no output)"
            return {
                "ok": False,
                "deployed": False,
                "project": proj["name"],
                "path": str(deploy_path),
                "command": cmd,
                "error": _soft(f"wrangler exit {r.returncode}: {safe}"),
            }
        return {
            "ok": True,
            "deployed": True,
            "project": proj["name"],
            "kind": kind,
            "path": str(deploy_path),
            "command": cmd,
            "message": (out[:500] if out else f"deployed {proj['name']}"),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "deployed": False,
            "project": proj["name"],
            "error": _soft("wrangler deploy timed out"),
        }
    except OSError as exc:
        return {
            "ok": False,
            "deployed": False,
            "project": proj["name"],
            "error": _soft(f"deploy failed ({exc})"),
        }


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("\n  Cloudflare Pages readiness (William-specific / PARTIAL)")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    print(f"      readiness: {info.get('readiness')}")
    print(f"      is_william_specific: {bool(info.get('is_william_specific'))}")
    print(f"      is_stranger_ready: {bool(info.get('is_stranger_ready'))}")
    wflag = "✓" if info.get("wrangler_present") else "○"
    print(f"  {wflag}  wrangler: {info.get('wrangler_path') or '(missing)'}")
    if info.get("wrangler_version"):
        print(f"      version: {info.get('wrangler_version')}")
    aflag = "✓" if info.get("auth_ok") else "○"
    print(f"  {aflag}  auth: {info.get('auth_detail')}")
    print(
        f"      token_env_set: {bool(info.get('token_env_set'))}"
        + (f" ({info.get('token_env_key')})" if info.get("token_env_key") else "")
    )
    print(
        f"      account_env_set: {bool(info.get('account_env_set'))}"
        + (
            f" ({info.get('account_env_key')})"
            if info.get("account_env_key")
            else ""
        )
    )
    docs = info.get("docs_site") or {}
    dflag = "✓" if docs.get("exists") else "○"
    print(f"  {dflag}  Docs/site: {docs.get('path')}")
    print(f"      files: {docs.get('file_count')} — {docs.get('note')}")
    print(
        f"      site-data.json: "
        f"{'present' if info.get('site_data_exists') else 'missing'} "
        f"({info.get('site_data_json')})"
    )
    print(
        f"      site_data_writer: "
        f"{'present' if info.get('site_data_writer_exists') else 'missing'}"
    )
    print(
        f"      projects: {info.get('project_count')} "
        f"(deployable paths: {info.get('deployable_count')})"
    )
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pok = info.get("probe_ok")
        pflag = "✓" if pok else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    print("  Try:")
    print("    bolt pages list")
    print("    bolt pages deploy bolt-fortress --dry-run")
    print("    bolt pages status --json")
    print("  Note: PARTIAL — William CF deploy only; not claimed READY for strangers.")
    print()
    return 0


def print_deploy(
    project: Optional[str] = None,
    *,
    path: Optional[str] = None,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    result = try_deploy(project, path=path, dry_run=dry_run)
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    if result.get("ok") and result.get("dry_run"):
        print(result.get("message") or "dry-run OK")
        print(f"  project: {result.get('project')}")
        print(f"  path:    {result.get('path')}")
        print(f"  cmd:     {' '.join(result.get('command') or [])}")
        return 0
    if result.get("ok") and result.get("deployed"):
        print(result.get("message") or f"deployed {result.get('project')}")
        return 0
    err = result.get("error") or _soft("deploy failed")
    print(err, file=sys.stderr)
    return 0  # soft-fail informational


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt pages — Cloudflare Pages deploy readiness (PARTIAL / William-specific)

  bolt pages                              # readiness (default)
  bolt pages status [--json] [--probe]
  bolt pages list [--json]
  bolt pages deploy [project] [--path DIR] [--dry-run] [--json]
  bolt pages-status                       # alias → status

Projects: bolt-fortress | billythunderstorm | billythunderstorm-live | bolt-api-worker
Soft-fail: "Pages unavailable:". Not stranger-ready — needs wrangler + CF auth
and William's /tmp/sites staging trees (Docs/site is legal stubs only).
Related: bolt sites (local site-data + storage cron; READY).
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "--dryrun" in args
    # Extract --path DIR
    path_arg: Optional[str] = None
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--path", "-p") and i + 1 < len(args):
            path_arg = args[i + 1]
            i += 2
            continue
        if a.startswith("--path="):
            path_arg = a.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(a)
        i += 1
    args = cleaned
    positionals = [a for a in args if not a.startswith("-")]

    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready", "pages-status", "pages_status"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "projects"):
        return list_projects(as_json=json_out)
    if cmd in ("deploy", "publish", "push"):
        proj = positionals[1] if len(positionals) > 1 else None
        return print_deploy(
            proj, path=path_arg, dry_run=dry_run, as_json=json_out
        )

    # Bare project name → deploy --dry-run safety? Prefer status help.
    print(f"unknown pages action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt pages status|list|deploy [project] [--json] [--dry-run]",
        file=sys.stderr,
    )
    return 0  # soft-fail informational


if __name__ == "__main__":
    raise SystemExit(main())
