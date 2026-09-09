#!/usr/bin/env python3
"""
Streamlabs_Monitor.py
=====================
Connects to the Streamlabs Socket API and fires a highlight callback
whenever a significant stream event occurs (donation, raid, subscription,
bits cheer, host).

Requirements
------------
    pip3 install "python-socketio[client]" python-dotenv

.env keys
---------
    STREAMLABS_SOCKET_TOKEN   <socket token from streamlabs.com/dashboard → Settings → API Settings → Socket API>
    MIN_RAID_SIZE             5     (minimum raiders to trigger a clip)
    MIN_BITS                  100   (minimum bits to trigger a clip)
    MIN_DONATION_USD          1.00  (minimum $ donation to trigger a clip)

Usage (standalone test)
-----------------------
    python -m modules.Streamlabs_Monitor

CLI
---
    bolt streamlabs status [--json] [--probe]
    Soft-fail when socketio / token missing (folder-watch still works).
"""

import os
import json
import time
import threading
import logging
from typing import Any, Callable, Dict, Optional

try:
    import socketio as sio_lib

    _SIO_OK = True
except ImportError:
    _SIO_OK = False

from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
SOCKET_TOKEN = os.getenv("STREAMLABS_SOCKET_TOKEN", "")
STREAMLABS_URL = "https://sockets.streamlabs.com"

MIN_RAID_SIZE = int(os.getenv("MIN_RAID_SIZE", "5"))
MIN_BITS = int(os.getenv("MIN_BITS", "100"))
MIN_DONATION = float(os.getenv("MIN_DONATION_USD", "1.00"))

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
class StreamlabsMonitor:
    """
    Listens for Streamlabs socket events and fires on_event / on_highlight
    callbacks so the rest of the pipeline can react.

    Parameters
    ----------
    on_highlight : callable(event_type: str, label: str, data: dict)
        Called for every event that crosses the configured thresholds.
    on_event : callable(event_type: str, data: dict)
        Called for *every* Streamlabs event regardless of threshold.
    """

    def __init__(
        self,
        on_highlight: Optional[Callable] = None,
        on_event: Optional[Callable] = None,
    ):
        self.on_highlight = on_highlight or (lambda *a, **kw: None)
        self.on_event = on_event or (lambda *a, **kw: None)
        self._sio = None
        self._thread = None
        self._running = False
        self._connected = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Connect to Streamlabs and begin listening in a background thread.
        Returns True if connection succeeded, False otherwise.
        """
        if not _SIO_OK:
            log.warning(
                "[Streamlabs] python-socketio not installed. "
                "Run: pip3 install 'python-socketio[client]'"
            )
            return False

        if not SOCKET_TOKEN:
            log.warning(
                "[Streamlabs] STREAMLABS_SOCKET_TOKEN not set in .env — "
                "Streamlabs integration disabled."
            )
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="streamlabs-monitor", daemon=True
        )
        self._thread.start()

        # Give it a moment to connect
        deadline = time.time() + 8
        while time.time() < deadline and not self._connected:
            time.sleep(0.2)

        if self._connected:
            print("[Streamlabs] ✓ Connected to Streamlabs Socket API")
        else:
            print("[Streamlabs] ✗ Could not connect — running without Streamlabs")

        return self._connected

    def stop(self):
        """Disconnect and shut down the background thread."""
        self._running = False
        if self._sio and self._connected:
            try:
                self._sio.disconnect()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        print("[Streamlabs] Disconnected.")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _run(self):
        """Background thread: build Socket.IO client and connect."""
        try:
            self._sio = sio_lib.Client(
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=2,
                logger=False,
                engineio_logger=False,
            )
            self._register_handlers()
            url = f"{STREAMLABS_URL}?token={SOCKET_TOKEN}"
            self._sio.connect(url, transports=["websocket"])
            self._sio.wait()  # blocks until disconnect
        except Exception as exc:
            log.error(f"[Streamlabs] Connection error: {exc}")
        finally:
            self._connected = False
            self._running = False

    def _register_handlers(self):
        sio = self._sio

        @sio.event
        def connect():
            self._connected = True
            log.info("[Streamlabs] socket connected")

        @sio.event
        def disconnect():
            self._connected = False
            log.info("[Streamlabs] socket disconnected")

        @sio.event
        def connect_error(data):
            log.error(f"[Streamlabs] connect_error: {data}")

        @sio.on("event")
        def on_raw_event(data):
            self._dispatch(data)

    def _dispatch(self, raw: dict):
        """Route incoming Streamlabs event to the right handler."""
        try:
            event_type = raw.get("type", "")
            message = raw.get("message", [{}])
            payload = message[0] if isinstance(message, list) and message else {}

            # Always fire the generic callback
            self.on_event(event_type, payload)

            if event_type == "donation":
                self._handle_donation(payload)
            elif event_type == "raid":
                self._handle_raid(payload)
            elif event_type == "subscription":
                self._handle_subscription(payload)
            elif event_type == "resub":
                self._handle_resub(payload)
            elif event_type == "bits":
                self._handle_bits(payload)
            elif event_type == "host":
                self._handle_host(payload)
            else:
                log.debug(f"[Streamlabs] Unhandled event type: {event_type}")

        except Exception as exc:
            log.error(f"[Streamlabs] Error dispatching event: {exc}")

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _handle_donation(self, p: dict):
        name = p.get("name", "Anonymous")
        amount = float(p.get("amount", 0))
        msg = p.get("message", "")
        label = f"💸 Donation ${amount:.2f} from {name}"
        if msg:
            label += f': "{msg}"'

        print(f"  [Streamlabs] {label}")

        if amount >= MIN_DONATION:
            self.on_highlight(
                "donation", label, {"donor": name, "amount": amount, "message": msg}
            )

    def _handle_raid(self, p: dict):
        raider = p.get("name", "Unknown")
        count = int(p.get("raiders", p.get("viewerCount", 0)))
        label = f"⚔️ Raid! {raider} brought {count} viewers"

        print(f"  [Streamlabs] {label}")

        if count >= MIN_RAID_SIZE:
            self.on_highlight("raid", label, {"raider": raider, "count": count})

    def _handle_subscription(self, p: dict):
        name = p.get("name", "Unknown")
        plan = p.get("sub_plan_name", p.get("sub_plan", ""))
        gifted = p.get("gifter_display_name", "")
        if gifted:
            label = f"🎁 Gift sub from {gifted} → {name} ({plan})"
        else:
            label = f"⭐ New sub: {name} ({plan})"

        print(f"  [Streamlabs] {label}")
        self.on_highlight(
            "subscription", label, {"subscriber": name, "plan": plan, "gifter": gifted}
        )

    def _handle_resub(self, p: dict):
        name = p.get("name", "Unknown")
        months = p.get("months", 1)
        label = f"🔄 Resub: {name} — {months} months"

        print(f"  [Streamlabs] {label}")
        # Only fire on milestone resubs (every 3 months, 6, 12, etc.)
        if int(months) % 3 == 0:
            self.on_highlight("resub", label, {"subscriber": name, "months": months})

    def _handle_bits(self, p: dict):
        name = p.get("name", "Anonymous")
        bits = int(p.get("amount", p.get("bits_used", 0)))
        msg = p.get("message", p.get("chat_message", ""))
        label = f"💎 {bits} bits from {name}"
        if msg:
            label += f': "{msg}"'

        print(f"  [Streamlabs] {label}")

        if bits >= MIN_BITS:
            self.on_highlight(
                "bits", label, {"viewer": name, "bits": bits, "message": msg}
            )

    def _handle_host(self, p: dict):
        hoster = p.get("name", "Unknown")
        viewers = int(p.get("viewers", 0))
        label = f"📡 Host: {hoster} ({viewers} viewers)"

        print(f"  [Streamlabs] {label}")

        if viewers >= MIN_RAID_SIZE:
            self.on_highlight("host", label, {"hoster": hoster, "viewers": viewers})


# ══════════════════════════════════════════════════════════════════════════════
# Readiness / CLI (bolt streamlabs)
# ══════════════════════════════════════════════════════════════════════════════

def _reload_token() -> str:
    """Re-read STREAMLABS_SOCKET_TOKEN (dotenv may load after import)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:
        pass
    return (os.getenv("STREAMLABS_SOCKET_TOKEN") or "").strip()


def status(*, probe: bool = False) -> Dict[str, Any]:
    """
    Streamlabs Socket API readiness. Never raises; never hangs on network
    unless probe=True (short connect, hard timeout).

    ready = python-socketio installed + STREAMLABS_SOCKET_TOKEN set.
    Live socket only reported when probe=True.
    Soft-fail: missing token / socketio → clear "Streamlabs unavailable:" hint.
    Folder-watch / clip pipeline still works without Streamlabs.
    """
    token = _reload_token()
    token_set = bool(token)
    # JWT-ish socket tokens are long; treat very short values as incomplete.
    token_looks_ok = token_set and len(token) >= 20

    info: Dict[str, Any] = {
        "ready": bool(_SIO_OK and token_looks_ok),
        "socketio_installed": bool(_SIO_OK),
        "token_set": token_set,
        "token_looks_ok": token_looks_ok,
        "url": STREAMLABS_URL,
        "min_raid_size": MIN_RAID_SIZE,
        "min_bits": MIN_BITS,
        "min_donation_usd": MIN_DONATION,
        "hint": "",
    }

    if not _SIO_OK:
        info["hint"] = (
            "Streamlabs unavailable: python-socketio not installed "
            "(uv sync / pip install 'python-socketio[client]'). "
            "Folder-watch clips still work."
        )
    elif not token_set:
        info["hint"] = (
            "Streamlabs unavailable: set STREAMLABS_SOCKET_TOKEN in .env "
            "(streamlabs.com/dashboard → Settings → API Settings → Socket API). "
            "Optional — folder-watch still works."
        )
    elif not token_looks_ok:
        info["hint"] = (
            "Streamlabs unavailable: STREAMLABS_SOCKET_TOKEN looks too short — "
            "paste the full Socket API token from the Streamlabs dashboard."
        )
    else:
        info["hint"] = (
            "Token + socketio ready. Live events need a valid Socket API token. "
            "Try: bolt streamlabs status --probe"
        )

    if probe:
        p = probe_streamlabs(timeout=5.0)
        info["probe_ok"] = bool(p.get("ok"))
        info["probe_detail"] = p.get("detail") or ""
        if p.get("ok"):
            info["hint"] = p["detail"]
        elif info["ready"]:
            info["hint"] = p.get("detail") or info["hint"]
        elif p.get("detail"):
            info["hint"] = p["detail"]

    return info


def probe_streamlabs(*, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Short Socket.IO connect probe. Never hangs longer than timeout.
    Does not leave a background listener running.
    """
    result: Dict[str, Any] = {"ok": False, "detail": ""}
    if not _SIO_OK:
        result["detail"] = "Streamlabs unavailable: python-socketio not installed"
        return result
    token = _reload_token()
    if not token:
        result["detail"] = "Streamlabs unavailable: STREAMLABS_SOCKET_TOKEN missing"
        return result
    if len(token) < 20:
        result["detail"] = "Streamlabs unavailable: STREAMLABS_SOCKET_TOKEN looks incomplete"
        return result

    connected = {"ok": False, "err": ""}

    def _run():
        client = None
        try:
            client = sio_lib.Client(
                reconnection=False,
                logger=False,
                engineio_logger=False,
            )

            @client.event
            def connect():
                connected["ok"] = True

            @client.event
            def connect_error(data):
                connected["err"] = str(data)[:200]

            url = f"{STREAMLABS_URL}?token={token}"
            client.connect(url, transports=["websocket"], wait_timeout=max(1.0, timeout - 0.5))
            # Brief settle, then disconnect
            deadline = time.time() + 1.5
            while time.time() < deadline and not connected["ok"]:
                time.sleep(0.1)
        except Exception as exc:
            connected["err"] = str(exc)[:200]
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass

    t = threading.Thread(target=_run, name="streamlabs-probe", daemon=True)
    t.start()
    t.join(timeout=timeout + 1.0)
    if t.is_alive():
        result["detail"] = (
            f"Streamlabs unavailable: probe timed out after {timeout:.0f}s "
            "(token may be invalid or network blocked)"
        )
        return result
    if connected["ok"]:
        result["ok"] = True
        result["detail"] = "ok — connected to Streamlabs Socket API (probe disconnected)"
        return result
    err = connected["err"] or "could not connect"
    result["detail"] = f"Streamlabs unavailable: {err}"
    return result


def _cli_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print("\n  Streamlabs Socket API readiness")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  ready: {bool(info.get('ready'))}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    print(f"  {'✓' if info.get('socketio_installed') else '○'}  python-socketio: {bool(info.get('socketio_installed'))}")
    print(f"  {'✓' if info.get('token_set') else '○'}  STREAMLABS_SOCKET_TOKEN set: {bool(info.get('token_set'))}")
    print(f"      token_looks_ok: {bool(info.get('token_looks_ok'))}")
    print(f"      thresholds: raid>={info.get('min_raid_size')} bits>={info.get('min_bits')} donation>=${info.get('min_donation_usd')}")
    if probe:
        pflag = "✓" if info.get("probe_ok") else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    print("  Try:")
    print("    bolt streamlabs status")
    print("    bolt streamlabs status --json")
    print("    bolt streamlabs status --probe   # short live connect (needs valid token)")
    print("  Note: optional — folder-watch / bolt recordings still work without Streamlabs.")
    print()
    return 0  # soft-fail informational


def _cli_help() -> int:
    print(
        """bolt streamlabs — Streamlabs Socket API readiness

  bolt streamlabs                 # readiness (default)
  bolt streamlabs status [--json] [--probe]

Soft-fail: missing python-socketio / STREAMLABS_SOCKET_TOKEN never hangs.
Live donations/raids/subs need a Socket API token from the Streamlabs dashboard.
Folder-watch clip pipeline still works without Streamlabs.
Aliases: streamlabs-status, slabs, streamlabs-monitor
"""
    )
    return 0


def main(argv=None) -> int:
    import sys

    args = list(argv) if argv is not None else sys.argv[1:]
    # Default / legacy standalone listen mode when --listen is passed
    if args and args[0] in ("-h", "--help", "help"):
        return _cli_help()
    if args and args[0] in ("listen", "--listen", "run"):
        return _cli_listen()
    if not args or args[0] in ("status", "ready", "check") or args[0] in ("--json", "--probe"):
        rest = args[1:] if args and args[0] in ("status", "ready", "check") else args
        as_json = "--json" in rest
        probe = "--probe" in rest
        unknown = [a for a in rest if a not in ("--json", "--probe")]
        if unknown:
            print(f"Unknown status flag(s): {' '.join(unknown)}", file=sys.stderr)
            return 2
        return _cli_status(as_json=as_json, probe=probe)
    print(f"Unknown arg: {args[0]}", file=sys.stderr)
    _cli_help()
    return 2


def _cli_listen() -> int:
    """Legacy: connect and print highlights until Ctrl+C."""
    logging.basicConfig(level=logging.INFO)

    def my_highlight(event_type, label, data):
        print(f"\n🎯 HIGHLIGHT → [{event_type.upper()}] {label}")
        print(f"   data: {json.dumps(data, indent=2)}")

    monitor = StreamlabsMonitor(on_highlight=my_highlight)
    ok = monitor.start()
    if not ok:
        print("\nStreamlabs unavailable: monitor could not start.")
        print("Set STREAMLABS_SOCKET_TOKEN in .env, or: bolt streamlabs status")
        return 1
    print("\nListening for Streamlabs events. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
