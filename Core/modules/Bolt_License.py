"""
Bolt_License.py — repo license readiness (PARTIAL)
==================================================
Honest status for the README license placeholder + LICENSE file.

This does **not** choose a license for you. Soft-fail prefix:
``License unavailable:``.

  bolt license                 # status (default)
  bolt license status [--json] [--probe]
  bolt license list [--json]
  bolt license show [--json]
  bolt license set <spdx> [--dry-run] [--json]   # writes LICENSE + patches README

Common SPDX ids: MIT, Apache-2.0, BSD-3-Clause, Unlicense, Proprietary
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_README = _REPO / "README.md"
_PLACEHOLDER = "[Add your preferred license here]"
# README uses a longer variant with an em dash / examples — match either.
_PLACEHOLDER_RE = re.compile(
    r"\[Add your preferred license here[^\]]*\]",
    re.IGNORECASE,
)
_LICENSE_CANDIDATES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")

# Short SPDX bodies (standard / public-domain texts). Proprietary = notice only.
_SPDX_BODIES: Dict[str, str] = {
    "MIT": """MIT License

Copyright (c) {year} {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""",
    "Apache-2.0": """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright (c) {year} {holder}

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
""",
    "BSD-3-Clause": """BSD 3-Clause License

Copyright (c) {year}, {holder}
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
""",
    "Unlicense": """This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>
""",
    "Proprietary": """Copyright (c) {year} {holder}. All rights reserved.

This software is proprietary. No license is granted to copy, modify,
distribute, or use this software except as expressly authorized in writing
by the copyright holder.
""",
}

_SPDX_ALIASES = {
    "mit": "MIT",
    "apache": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache2": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd-3": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "unlicense": "Unlicense",
    "public-domain": "Unlicense",
    "proprietary": "Proprietary",
    "all-rights-reserved": "Proprietary",
    "private": "Proprietary",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _year() -> str:
    return str(datetime.now().year)


def _holder() -> str:
    import os

    return (
        os.environ.get("BOLT_LICENSE_HOLDER")
        or os.environ.get("BOLT_OWNER_NAME")
        or "William Carter"
    ).strip() or "William Carter"


def find_license_file(root: Optional[Path] = None) -> Optional[Path]:
    base = root or _REPO
    for name in _LICENSE_CANDIDATES:
        p = base / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def readme_has_placeholder(root: Optional[Path] = None) -> bool:
    readme = (root or _REPO) / "README.md"
    if not readme.is_file():
        return False
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_PLACEHOLDER_RE.search(text)) or (_PLACEHOLDER in text)


def detect_spdx(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "mit license" in t or ("permission is hereby granted" in t and "without warranty" in t):
        return "MIT"
    if "apache license" in t and "2.0" in t:
        return "Apache-2.0"
    if "bsd 3-clause" in t or ("redistribution and use" in t and "neither the name" in t):
        return "BSD-3-Clause"
    if "unlicense" in t or "unencumbered software released into the public domain" in t:
        return "Unlicense"
    if "all rights reserved" in t and "proprietary" in t:
        return "Proprietary"
    if "all rights reserved" in t and "no license is granted" in t:
        return "Proprietary"
    return None


def normalize_spdx(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    if s in _SPDX_BODIES:
        return s
    return _SPDX_ALIASES.get(s.lower().replace("_", "-").replace(" ", "-"))


def list_spdx() -> List[Dict[str, str]]:
    return [
        {"id": "MIT", "summary": "Permissive; keep copyright + permission notice"},
        {"id": "Apache-2.0", "summary": "Permissive; patent grant; NOTICE file friendly"},
        {"id": "BSD-3-Clause", "summary": "Permissive; no endorsement clause"},
        {"id": "Unlicense", "summary": "Public-domain dedication"},
        {"id": "Proprietary", "summary": "All rights reserved; no open grant"},
    ]


def status(*, probe: bool = False, root: Optional[Path] = None) -> Dict[str, Any]:
    base = root or _REPO
    try:
        lic = find_license_file(base)
        placeholder = readme_has_placeholder(base)
        readme = base / "README.md"
        spdx = None
        lic_bytes = 0
        lic_path = None
        if lic is not None:
            lic_path = str(lic)
            try:
                body = lic.read_text(encoding="utf-8", errors="replace")
                lic_bytes = len(body.encode("utf-8"))
                spdx = detect_spdx(body)
            except OSError as exc:
                return {
                    "ready": False,
                    "readiness": "PARTIAL",
                    "is_stranger_ready": False,
                    "placeholder_present": placeholder,
                    "license_file": None,
                    "hint": f"License unavailable: cannot read {lic.name} ({exc})",
                    "checked_at": _utc_now(),
                }

        # ready = tooling works AND a real LICENSE is present with placeholder cleared
        ready = bool(lic) and not placeholder
        hint = None
        if not lic and placeholder:
            hint = (
                "License unavailable: no LICENSE file and README still has "
                f"{_PLACEHOLDER!r} — try: bolt license list && bolt license set MIT"
            )
        elif not lic:
            hint = (
                "License unavailable: no LICENSE / LICENSE.md at repo root — "
                "try: bolt license list && bolt license set <spdx>"
            )
        elif placeholder:
            hint = (
                "License unavailable: LICENSE present but README still has "
                f"{_PLACEHOLDER!r} — re-run: bolt license set {spdx or 'MIT'}"
            )

        out: Dict[str, Any] = {
            "ready": ready,
            "readiness": "PARTIAL",
            "is_stranger_ready": False,
            "placeholder_present": placeholder,
            "readme_path": str(readme) if readme.is_file() else None,
            "license_file": lic_path,
            "license_bytes": lic_bytes,
            "detected_spdx": spdx,
            "supported_spdx": [x["id"] for x in list_spdx()],
            "hint": hint,
            "checked_at": _utc_now(),
        }

        if probe:
            try:
                if lic is not None:
                    _ = lic.read_text(encoding="utf-8", errors="replace")[:200]
                    out["probe_ok"] = True
                    out["probe_detail"] = f"read {lic.name} ok ({lic_bytes} bytes)"
                elif readme.is_file():
                    text = readme.read_text(encoding="utf-8", errors="replace")
                    out["probe_ok"] = bool(_PLACEHOLDER_RE.search(text)) or (_PLACEHOLDER in text)
                    out["probe_detail"] = (
                        "README placeholder still present"
                        if out["probe_ok"]
                        else "README readable; placeholder already gone (still no LICENSE)"
                    )
                else:
                    out["probe_ok"] = False
                    out["probe_detail"] = "License unavailable: missing README.md"
            except OSError as exc:
                out["probe_ok"] = False
                out["probe_detail"] = f"License unavailable: probe failed ({exc})"
        return out
    except Exception as exc:  # noqa: BLE001 — soft-fail status
        return {
            "ready": False,
            "readiness": "PARTIAL",
            "is_stranger_ready": False,
            "hint": f"License unavailable: status failed ({exc})",
            "error": str(exc),
            "checked_at": _utc_now(),
        }


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("\n  License readiness (PARTIAL — choose SPDX to finish)")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    print(f"      readiness: {info.get('readiness')}")
    print(f"      is_stranger_ready: {bool(info.get('is_stranger_ready'))}")
    print(f"      placeholder_present: {bool(info.get('placeholder_present'))}")
    print(f"      license_file: {info.get('license_file') or '(none)'}")
    print(f"      detected_spdx: {info.get('detected_spdx') or '(unknown)'}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pok = info.get("probe_ok")
        pflag = "✓" if pok else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    print("  Try:")
    print("    bolt license list")
    print("    bolt license set MIT          # or Apache-2.0 / Proprietary")
    print("    bolt license set MIT --dry-run")
    print("    bolt license status --json")
    print("  Note: does not auto-pick a license; set is explicit.")
    print()
    return 0


def list_licenses(*, as_json: bool = False) -> int:
    rows = list_spdx()
    if as_json:
        print(json.dumps({"ok": True, "licenses": rows}, indent=2))
        return 0
    print("\n  Supported SPDX ids for bolt license set")
    print("  " + "─" * 40)
    for row in rows:
        print(f"  •  {row['id']}")
        print(f"      {row['summary']}")
    print()
    print("  Example: bolt license set MIT")
    print()
    return 0


def show_license(*, as_json: bool = False) -> int:
    info = status()
    lic = find_license_file()
    if lic is None:
        msg = info.get("hint") or "License unavailable: no LICENSE file"
        if as_json:
            print(json.dumps({"ok": False, "error": msg, **info}, indent=2, default=str))
        else:
            print(msg, file=sys.stderr)
        return 0
    try:
        text = lic.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        msg = f"License unavailable: cannot read {lic.name} ({exc})"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0
    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "path": str(lic),
                    "detected_spdx": detect_spdx(text),
                    "body": text,
                },
                indent=2,
                default=str,
            )
        )
        return 0
    print()
    print(text.rstrip())
    print()
    return 0


def _patch_readme(readme: Path, spdx: str, *, dry_run: bool) -> Tuple[bool, str]:
    if not readme.is_file():
        return False, "License unavailable: missing README.md"
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"License unavailable: cannot read README.md ({exc})"

    replacement = f"{spdx} (see `LICENSE`)"
    if _PLACEHOLDER_RE.search(text):
        new = _PLACEHOLDER_RE.sub(replacement, text, count=1)
    elif _PLACEHOLDER in text:
        new = text.replace(_PLACEHOLDER, replacement)
    else:
        # Already patched or different wording — leave body alone
        new = text

    if new == text and not readme_has_placeholder(readme.parent):
        return True, "README already without placeholder"

    if dry_run:
        return True, f"would replace placeholder with {replacement!r}"

    try:
        readme.write_text(new, encoding="utf-8")
    except OSError as exc:
        return False, f"License unavailable: cannot write README.md ({exc})"
    return True, f"README placeholder → {replacement!r}"


def try_set(
    spdx_raw: str,
    *,
    dry_run: bool = False,
    as_json: bool = False,
    holder: Optional[str] = None,
) -> int:
    spdx = normalize_spdx(spdx_raw)
    if not spdx:
        msg = (
            "License unavailable: unknown SPDX "
            f"{(spdx_raw or '').strip()!r} — try: bolt license list"
        )
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    body = _SPDX_BODIES[spdx].format(year=_year(), holder=(holder or _holder()))
    dest = _REPO / "LICENSE"
    existing = find_license_file()

    if dry_run:
        readme_ok, readme_msg = _patch_readme(_README, spdx, dry_run=True)
        payload = {
            "ok": True,
            "dry_run": True,
            "spdx": spdx,
            "would_write": str(dest),
            "existing_license": str(existing) if existing else None,
            "readme": readme_msg,
            "bytes": len(body.encode("utf-8")),
        }
        if as_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"License dry-run: would write {dest} ({spdx}, {payload['bytes']} bytes)")
            if existing:
                print(f"  existing: {existing}")
            print(f"  README: {readme_msg}")
        return 0

    try:
        dest.write_text(body, encoding="utf-8")
    except OSError as exc:
        msg = f"License unavailable: cannot write {dest} ({exc})"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    readme_ok, readme_msg = _patch_readme(_README, spdx, dry_run=False)
    if not readme_ok:
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": readme_msg,
                        "license_written": str(dest),
                        "spdx": spdx,
                    },
                    indent=2,
                )
            )
        else:
            print(readme_msg, file=sys.stderr)
            print(f"  (LICENSE written to {dest})", file=sys.stderr)
        return 0

    info = status()
    payload = {
        "ok": True,
        "spdx": spdx,
        "license_file": str(dest),
        "readme": readme_msg,
        "ready": bool(info.get("ready")),
        "hint": info.get("hint"),
    }
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"Wrote {dest} ({spdx})")
        print(f"  README: {readme_msg}")
        if info.get("ready"):
            print("  status: ready=true (still documented as PARTIAL until you want green)")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt license — repo license readiness (PARTIAL)

  bolt license                       # readiness (default)
  bolt license status [--json] [--probe]
  bolt license list [--json]
  bolt license show [--json]
  bolt license set <spdx> [--dry-run] [--json]

Soft-fail: "License unavailable:". Does not auto-pick a license.
Supported: MIT, Apache-2.0, BSD-3-Clause, Unlicense, Proprietary.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "options", "spdx"):
        return list_licenses(as_json=json_out)
    if cmd in ("show", "read", "cat", "view"):
        return show_license(as_json=json_out)
    if cmd in ("set", "apply", "choose", "write"):
        if len(positionals) < 2:
            msg = "License unavailable: set needs an SPDX id — try: bolt license list"
            if json_out:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        return try_set(positionals[1], dry_run=dry_run, as_json=json_out)

    # Bare SPDX → set with soft confirmation path? No — require explicit set.
    print(f"unknown license action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt license status|list|show|set <spdx> [--json] [--dry-run]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
