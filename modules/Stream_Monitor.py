#!/usr/bin/env python3
"""
modules/Stream_Monitor.py — OBS WebSocket 5.x monitor
======================================================
Connects to OBS WebSocket 5.x, authenticates, subscribes to events,
and triggers callbacks on:
  - Audio volume spikes (replay buffer save)
  - ReplayBufferSaved (clip file ready)
  - StreamStateChanged (stream start/stop)
  - RecordStateChanged (recording start/stop)
"""

import os
import json
import time
import base64
import hashlib
import threading
from typing import Optional, Callable

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

# OBS WebSocket 5.x eventSubscriptions bitmask
# Bit 0  = General, Bit 1 = Config, Bit 4 = Outputs, Bit 5 = SceneItems,
# Bit 16 = InputVolumeMeters
EVENT_SUBSCRIPTIONS = (
    (1 << 0)   # General
    | (1 << 4)  # Outputs (replay buffer, stream, record)
    | (1 << 5)  # SceneItems
    | (1 << 16) # InputVolumeMeters
)  # = 67617


class StreamMonitor:
    """
    Long-running OBS WebSocket 5.x client.

    Callbacks
    ---------
    on_replay_saved(path: str)   — called when replay buffer is saved
    on_spike(level_db: float)    — called when volume exceeds threshold
    on_stream_start()
    on_stream_stop()
    on_record_start()
    on_record_stop(path: str)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: Optional[str] = None,
        spike_threshold_db: float = -20.0,
        spike_multiplier: float = 2.8,
        on_replay_saved: Optional[Callable] = None,
        on_spike: Optional[Callable] = None,
        on_stream_start: Optional[Callable] = None,
        on_stream_stop: Optional[Callable] = None,
        on_record_start: Optional[Callable] = None,
        on_record_stop: Optional[Callable] = None,
    ):
        self.host = host
        self.port = port
        self.password = password or os.getenv("OBS_PASSWORD", "")
        self.spike_threshold_db = spike_threshold_db
        self.spike_multiplier = spike_multiplier

        self.on_replay_saved  = on_replay_saved  or (lambda path: None)
        self.on_spike         = on_spike         or (lambda db: None)
        self.on_stream_start  = on_stream_start  or (lambda: None)
        self.on_stream_stop   = on_stream_stop   or (lambda: None)
        self.on_record_start  = on_record_start  or (lambda: None)
        self.on_record_stop   = on_record_stop   or (lambda path: None)

        self._ws: Optional[object] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._rms_history: list = []   # rolling window for spike detection
        self._request_id = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        """Connect and begin listening in a background thread."""
        if not HAS_WEBSOCKET:
            notify(
                "websocket-client not installed — OBS monitoring disabled",
                level="warning",
                reason="Install with: pip3 install websocket-client"
            )
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        notify(
            f"OBS WebSocket monitor starting on {self.host}:{self.port}",
            level="info",
            reason="Running in a background thread so Bolt can watch the recordings "
                   "folder at the same time. The WebSocket stays connected for the "
                   "entire stream session."
        )

    def stop(self):
        """Disconnect and stop the background thread."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        notify("OBS WebSocket monitor stopped.", level="info")

    def save_replay(self):
        """Ask OBS to save the replay buffer right now."""
        self._send_request("SaveReplayBuffer")
        notify(
            "Replay buffer save requested",
            level="info",
            reason="OBS will write the last N seconds of footage to disk. "
                   "ReplayBufferSaved event will fire when the file is ready."
        )

    # ── WebSocket thread ───────────────────────────────────────────────────────

    def _run(self):
        url = f"ws://{self.host}:{self.port}"
        retry_delay = 5

        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:
                notify(f"OBS WebSocket error: {exc}", level="warning",
                       reason=f"Will retry in {retry_delay}s. "
                              "Check OBS is open and WebSocket Server is enabled.")
            if self._running:
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def _on_open(self, ws):
        notify("OBS WebSocket connected — waiting for Hello", level="info",
               reason="OBS sends a Hello message first with auth challenge. "
                      "Bolt will respond with Identify to complete the handshake.")

    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        op = msg.get("op")

        # Hello (op=0) — send Identify
        if op == 0:
            self._handle_hello(msg["d"])

        # Identified (op=2) — authenticated
        elif op == 2:
            notify(
                "OBS WebSocket authenticated ✓",
                level="success",
                reason="Bolt is now subscribed to OBS events including "
                       "ReplayBufferSaved, StreamStateChanged, RecordStateChanged, "
                       "and InputVolumeMeters for audio spike detection."
            )

        # Event (op=5)
        elif op == 5:
            self._handle_event(msg["d"])

        # RequestResponse (op=7)
        elif op == 7:
            self._handle_response(msg["d"])

    def _on_error(self, ws, error):
        notify(f"OBS WebSocket error: {error}", level="warning")

    def _on_close(self, ws, code, reason):
        if self._running:
            notify(f"OBS WebSocket closed ({code}) — reconnecting…", level="warning",
                   reason="Connection lost. This can happen if OBS crashes or is restarted. "
                          "Bolt will reconnect automatically.")

    # ── OBS protocol ──────────────────────────────────────────────────────────

    def _handle_hello(self, data: dict):
        auth = data.get("authentication")
        auth_str = ""
        if auth and self.password:
            secret = base64.b64encode(
                hashlib.sha256(
                    (self.password + auth["salt"]).encode()
                ).digest()
            ).decode()
            auth_str = base64.b64encode(
                hashlib.sha256(
                    (secret + auth["challenge"]).encode()
                ).digest()
            ).decode()

        identify = {
            "op": 1,
            "d": {
                "rpcVersion": 1,
                "authentication": auth_str,
                "eventSubscriptions": EVENT_SUBSCRIPTIONS,
            }
        }
        self._ws.send(json.dumps(identify))

    def _handle_event(self, data: dict):
        event_type = data.get("eventType", "")
        event_data = data.get("eventData", {})

        if event_type == "ReplayBufferSaved":
            path = event_data.get("savedReplayPath", "")
            notify(
                f"Replay buffer saved: {path}",
                level="success",
                reason="OBS has written the clip to disk. Bolt's Watcher will pick "
                       "it up from the recordings folder and begin processing."
            )
            self.on_replay_saved(path)

        elif event_type == "StreamStateChanged":
            state = event_data.get("outputState", "")
            if state == "OBS_WEBSOCKET_OUTPUT_STARTED":
                notify("Stream started ✓", level="success",
                       reason="Bolt is now monitoring audio levels and chat activity.")
                self.on_stream_start()
            elif state == "OBS_WEBSOCKET_OUTPUT_STOPPED":
                notify("Stream stopped.", level="info")
                self.on_stream_stop()

        elif event_type == "RecordStateChanged":
            state = event_data.get("outputState", "")
            if state == "OBS_WEBSOCKET_OUTPUT_STARTED":
                notify("Recording started ✓", level="success")
                self.on_record_start()
            elif state == "OBS_WEBSOCKET_OUTPUT_STOPPED":
                path = event_data.get("outputPath", "")
                notify(f"Recording saved: {path}", level="success",
                       reason="Full recording is ready. If auto-processing is enabled, "
                              "Bolt will scan it for highlights now.")
                self.on_record_stop(path)

        elif event_type == "InputVolumeMeters":
            self._check_volume_spike(event_data)

    def _check_volume_spike(self, data: dict):
        """
        InputVolumeMeters fires ~60x/sec with per-channel RMS levels.
        Detect a spike when current level exceeds rolling average × spike_multiplier.
        """
        inputs = data.get("inputs", [])
        for inp in inputs:
            levels = inp.get("inputLevelsMul", [])
            if not levels:
                continue
            # levels is [[left_mul, right_mul], ...] per channel
            try:
                max_mul = max(
                    max(ch) for ch in levels if ch
                )
            except (ValueError, TypeError):
                continue

            self._rms_history.append(max_mul)
            if len(self._rms_history) > 300:  # ~5s window at 60fps
                self._rms_history.pop(0)

            if len(self._rms_history) < 60:
                continue  # warm-up period

            avg = sum(self._rms_history[:-30]) / max(len(self._rms_history[:-30]), 1)
            if avg == 0:
                continue

            ratio = max_mul / avg
            if ratio >= self.spike_multiplier:
                import math
                db = 20 * math.log10(max_mul) if max_mul > 0 else -100
                if db >= self.spike_threshold_db:
                    notify(
                        f"Audio spike detected: {db:.1f} dB (ratio {ratio:.1f}×)",
                        level="info",
                        reason=f"Volume jumped {ratio:.1f}× above the rolling average. "
                               f"spike_multiplier threshold = {self.spike_multiplier}. "
                               "Requesting replay buffer save."
                    )
                    self.on_spike(db)
                    self._rms_history.clear()  # debounce

    def _handle_response(self, data: dict):
        pass  # response logging if needed

    def _send_request(self, request_type: str, fields: dict = None):
        self._request_id += 1
        msg = {
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId": str(self._request_id),
                "requestData": fields or {},
            }
        }
        if self._ws:
            try:
                self._ws.send(json.dumps(msg))
            except Exception as exc:
                notify(f"Failed to send {request_type}: {exc}", level="warning")
