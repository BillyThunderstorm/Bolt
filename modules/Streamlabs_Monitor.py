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
    STREAMLABS_SOCKET_TOKEN   <your socket token from streamlabs.com/dashboard#/eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbiI6Ijk3Nzk3RURFOTNFNTlFRDQ2Q0U5NDUzNDY0M0UxODUzQUUwNjBGNTg3MThGMkMzQkZDOTNENTkxMDY3QUIxODY0QTQxOUQxQjBCQ0JFREJFMTM2QUIzOTk2RDM5MDQ0QTlEQzBFNUMzMzRDODNGMEFBRkQ1N0Q2OUFFQTI3M0JGNzk4OUUwNDUyOTMwQjUxRUY1Q0EzMTZGNEQyNDU1NEQwMEVERUI1Nzg4RUY2RjNBQUY3MTIxNjIzQjgyQ0EwRjcwRjdGMDYyRTg3NzFCMzhEODU1RUI5OUQ2QjdEMUUyRTA0NTFFNUI3OEYxOUYxRDlFQ0JFQ0QyODciLCJyZWFkX29ubHkiOnRydWUsInByZXZlbnRfbWFzdGVyIjp0cnVlLCJ0d2l0Y2hfaWQiOiI0NDE1OTg3NjUiLCJzdHJlYW1sYWJzX2lkIjoiNzMwNTA1MDg2OTk4MzA4NDU0NCIsInlvdXR1YmVfaWQiOiJVQzBfenZIQ25pMEVidFplRWFobnFvMVEiLCJ0aWt0b2tfaWQiOiI1ZWFjNjFlNy02ZGY5LTVhNDktODE2My0zMTQ2Zjc5NzZhOWQiLCJraWNrX2lkIjoiODY2NTc3NTciLCJ0d2l0dGVyX2lkIjoiMTk3NDgzMDY5OTU4MTQ3Mjc2OCJ9.aypktgnX5ZtCjgn6EWRYQvzMGF3huh5tycrQD5DMejAsettings/api-settings>
    MIN_RAID_SIZE             5     (minimum raiders to trigger a clip)
    MIN_BITS                  100   (minimum bits to trigger a clip)
    MIN_DONATION_USD          1.00  (minimum $ donation to trigger a clip)

Usage (standalone test)
-----------------------
    python -m modules.Streamlabs_Monitor
"""

import os
import json
import time
import threading
import logging
from typing import Callable, Optional

try:
    import socketio as sio_lib
    _SIO_OK = True
except ImportError:
    _SIO_OK = False

from dotenv import load_dotenv
load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
SOCKET_TOKEN    = os.getenv("STREAMLABS_SOCKET_TOKEN", "")
STREAMLABS_URL  = "https://sockets.streamlabs.com"

MIN_RAID_SIZE   = int(os.getenv("MIN_RAID_SIZE",    "5"))
MIN_BITS        = int(os.getenv("MIN_BITS",         "100"))
MIN_DONATION    = float(os.getenv("MIN_DONATION_USD", "1.00"))

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
        on_event:     Optional[Callable] = None,
    ):
        self.on_highlight = on_highlight or (lambda *a, **kw: None)
        self.on_event     = on_event     or (lambda *a, **kw: None)
        self._sio         = None
        self._thread      = None
        self._running     = False
        self._connected   = False

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
        self._thread  = threading.Thread(
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
            self._sio.wait()          # blocks until disconnect
        except Exception as exc:
            log.error(f"[Streamlabs] Connection error: {exc}")
        finally:
            self._connected = False
            self._running   = False

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
            message    = raw.get("message", [{}])
            payload    = message[0] if isinstance(message, list) and message else {}

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
        name   = p.get("name", "Anonymous")
        amount = float(p.get("amount", 0))
        msg    = p.get("message", "")
        label  = f"💸 Donation ${amount:.2f} from {name}"
        if msg:
            label += f': "{msg}"'

        print(f"  [Streamlabs] {label}")

        if amount >= MIN_DONATION:
            self.on_highlight("donation", label, {
                "donor": name, "amount": amount, "message": msg
            })

    def _handle_raid(self, p: dict):
        raider = p.get("name", "Unknown")
        count  = int(p.get("raiders", p.get("viewerCount", 0)))
        label  = f"⚔️ Raid! {raider} brought {count} viewers"

        print(f"  [Streamlabs] {label}")

        if count >= MIN_RAID_SIZE:
            self.on_highlight("raid", label, {
                "raider": raider, "count": count
            })

    def _handle_subscription(self, p: dict):
        name    = p.get("name", "Unknown")
        plan    = p.get("sub_plan_name", p.get("sub_plan", ""))
        gifted  = p.get("gifter_display_name", "")
        if gifted:
            label = f"🎁 Gift sub from {gifted} → {name} ({plan})"
        else:
            label = f"⭐ New sub: {name} ({plan})"

        print(f"  [Streamlabs] {label}")
        self.on_highlight("subscription", label, {
            "subscriber": name, "plan": plan, "gifter": gifted
        })

    def _handle_resub(self, p: dict):
        name   = p.get("name", "Unknown")
        months = p.get("months", 1)
        label  = f"🔄 Resub: {name} — {months} months"

        print(f"  [Streamlabs] {label}")
        # Only fire on milestone resubs (every 3 months, 6, 12, etc.)
        if int(months) % 3 == 0:
            self.on_highlight("resub", label, {
                "subscriber": name, "months": months
            })

    def _handle_bits(self, p: dict):
        name  = p.get("name", "Anonymous")
        bits  = int(p.get("amount", p.get("bits_used", 0)))
        msg   = p.get("message", p.get("chat_message", ""))
        label = f"💎 {bits} bits from {name}"
        if msg:
            label += f': "{msg}"'

        print(f"  [Streamlabs] {label}")

        if bits >= MIN_BITS:
            self.on_highlight("bits", label, {
                "viewer": name, "bits": bits, "message": msg
            })

    def _handle_host(self, p: dict):
        hoster  = p.get("name", "Unknown")
        viewers = int(p.get("viewers", 0))
        label   = f"📡 Host: {hoster} ({viewers} viewers)"

        print(f"  [Streamlabs] {label}")

        if viewers >= MIN_RAID_SIZE:
            self.on_highlight("host", label, {
                "hoster": hoster, "viewers": viewers
            })


# ══════════════════════════════════════════════════════════════════════════════
# Standalone test
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def my_highlight(event_type, label, data):
        print(f"\n🎯 HIGHLIGHT → [{event_type.upper()}] {label}")
        print(f"   data: {json.dumps(data, indent=2)}")

    monitor = StreamlabsMonitor(on_highlight=my_highlight)
    ok = monitor.start()

    if not ok:
        print("\nStreamlabs monitor could not start.")
        print("Make sure STREAMLABS_SOCKET_TOKEN is set in your .env file.")
    else:
        print("\nListening for Streamlabs events. Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            monitor.stop()
