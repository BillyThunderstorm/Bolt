"""Targeted tests for bolt obs-game (OBS_Game_Tracker + scripts/update_game_from_obs.py).

Temp files + fakes only: never touches the real Core/config.json, the real
mapping, Twitch, or OBS.
"""
import contextlib
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
import modules.OBS_Game_Tracker as OGT  # noqa: E402
import modules.Game_Refresh as GR  # noqa: E402

ENG = OGT._load_engine()

MAPPING = {
    "live_scene": "Live Scene",
    "scenes": {"Live Scene": "__twitch__", "Be Right Back": "Just Chatting", "Racing": "Forza Horizon 5"},
}


def _setup(tmp_path, monkeypatch, game="Old Game"):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"game": game, "obs_port": 4455, "other": {"keep": [1, 2]}}, indent=2) + "\n")
    mp = tmp_path / "scene_game_mapping.json"
    mp.write_text(json.dumps(MAPPING, indent=2))
    log = tmp_path / "obs_game_tracker.jsonl"
    for mod, names in ((ENG, ("CONFIG_FILE", "MAPPING_FILE", "CHANGE_LOG")), (GR, ("_CONFIG", "_MAPPING", "_STATE"))):
        for n in names:
            target = {"CONFIG_FILE": cfg, "_CONFIG": cfg, "MAPPING_FILE": mp, "_MAPPING": mp,
                      "CHANGE_LOG": log, "_STATE": tmp_path / "game_state.json"}[n]
            monkeypatch.setattr(mod, n, target)
    monkeypatch.setattr(ENG, "_twitch_game", lambda: {"game": "", "error": "offline in tests"})
    return cfg, log


def test_lookup_exact_loose_none():
    assert ENG.lookup_scene("Racing", MAPPING) == ("Forza Horizon 5", "Racing", "exact")
    assert ENG.lookup_scene("Be Right Back(1)", MAPPING)[2] == "loose"
    assert ENG.lookup_scene("  live   SCENE ", MAPPING)[0] == "__twitch__"
    assert ENG.lookup_scene("Offline", MAPPING) == (None, "", "none")


def test_sync_writes_atomically_keeps_keys_and_logs(tmp_path, monkeypatch):
    cfg, log = _setup(tmp_path, monkeypatch)
    r = ENG.sync_scene("racing", trigger="test")
    assert r["ok"] and r["changed"] and r["before"] == "Old Game" and r["after"] == "Forza Horizon 5"
    data = json.loads(cfg.read_text())
    assert data["game"] == "Forza Horizon 5" and data["other"] == {"keep": [1, 2]} and data["obs_port"] == 4455
    assert not (tmp_path / "config.json.tmp").exists()
    assert json.loads(log.read_text().splitlines()[-1])["changed"] is True
    assert json.loads((tmp_path / "game_state.json").read_text())["game"] == "Forza Horizon 5"


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    cfg, _ = _setup(tmp_path, monkeypatch)
    before = cfg.read_text()
    r = ENG.sync_scene("Racing", dry_run=True)
    assert r["ok"] and r["would_change"] and not r["changed"]
    assert cfg.read_text() == before


def test_twitch_sentinel(tmp_path, monkeypatch):
    cfg, _ = _setup(tmp_path, monkeypatch)
    r = ENG.sync_scene("Live Scene")  # Twitch offline → keep
    assert r["ok"] and not r["changed"] and json.loads(cfg.read_text())["game"] == "Old Game"
    monkeypatch.setattr(ENG, "_twitch_game", lambda: {"game": "Hades II", "error": ""})
    r = ENG.sync_scene("Live Scene")
    assert r["changed"] and json.loads(cfg.read_text())["game"] == "Hades II"


def test_unmapped_scene_leaves_game(tmp_path, monkeypatch):
    cfg, _ = _setup(tmp_path, monkeypatch)
    r = ENG.sync_scene("Offline")
    assert r["ok"] and not r["changed"] and "isn't in the mapping" in r["message"]
    assert json.loads(cfg.read_text())["game"] == "Old Game"


# ── OBS connection soft-fails (fake socket / websocket) ─────────────────────


class _FakeWS:
    def __init__(self, auth=True, accept=True, scene="Racing"):
        self.auth, self.accept, self.scene, self.sent = auth, accept, scene, []
        self._queue = [json.dumps({"op": 0, "d": {"authentication": {"salt": "s", "challenge": "c"}} if auth else {}})]

    def settimeout(self, t):
        pass

    def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg["op"] == 1:
            if not self.accept:
                self._queue.append("CLOSED")
            else:
                self._queue.append(json.dumps({"op": 2, "d": {}}))
        elif msg["op"] == 6:
            rid = msg["d"]["requestId"]
            data = ({"currentProgramSceneName": self.scene} if msg["d"]["requestType"] == "GetCurrentProgramScene"
                    else {"scenes": [{"sceneName": self.scene}]})
            self._queue.append(json.dumps({"op": 7, "d": {"requestId": rid, "requestStatus": {"result": True},
                                                          "responseData": data}}))

    def recv(self):
        item = self._queue.pop(0)
        if item == "CLOSED":
            raise ConnectionError("closed 4009")
        return item

    def close(self):
        pass


def _fake_obs(monkeypatch, ws=None, port_open=True, password="pw"):
    import socket

    def fake_conn(addr, timeout=None):
        if not port_open:
            raise ConnectionRefusedError("refused")
        return contextlib.nullcontext()

    monkeypatch.setattr(socket, "create_connection", fake_conn)
    fake_mod = types.SimpleNamespace(create_connection=lambda url, timeout=None: ws)
    monkeypatch.setitem(sys.modules, "websocket", fake_mod)
    monkeypatch.setattr(ENG, "obs_settings", lambda: {"host": "localhost", "port": 4455, "password": password,
                                                      "password_set": bool(password), "use_obs_integration": True})


def test_obs_closed_soft_fail(monkeypatch):
    _fake_obs(monkeypatch, port_open=False)
    s = ENG.obs_snapshot(timeout=0.1)
    assert not s["ok"] and "Tools → WebSocket Server Settings" in s["fix"]


def test_obs_missing_and_wrong_password(monkeypatch):
    _fake_obs(monkeypatch, ws=_FakeWS(), password="")
    s = ENG.obs_snapshot()
    assert not s["ok"] and "OBS_PASSWORD" in s["fix"] and ".env.local" in s["fix"]
    _fake_obs(monkeypatch, ws=_FakeWS(accept=False), password="wrong")
    s = ENG.obs_snapshot()
    assert not s["ok"] and "rejected" in s["error"]


def test_obs_scene_and_run_once(tmp_path, monkeypatch):
    cfg, _ = _setup(tmp_path, monkeypatch)
    ws = _FakeWS(scene="Racing")
    _fake_obs(monkeypatch, ws=ws)
    r = ENG.sync_once()
    assert r["ok"] and r["scene"] == "Racing" and json.loads(cfg.read_text())["game"] == "Forza Horizon 5"
    # read-only: only Identify + GetCurrentProgramScene were sent
    assert [m["d"].get("requestType") for m in ws.sent if m["op"] == 6] == ["GetCurrentProgramScene"]


def test_status_json_shows_match(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch, game="Forza Horizon 5")
    monkeypatch.setattr(ENG, "obs_snapshot", lambda **k: {"ok": True, "scene": "Racing", "scenes": [],
                                                          "error": "", "fix": ""})
    OGT.main(["status", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["obs_scene"] == "Racing" and out["mapped_game"] == "Forza Horizon 5" and out["match"] is True


def test_env_local_wins(tmp_path, monkeypatch):
    (tmp_path / ".env.local").write_text("OBS_PASSWORD=from_local\n")
    (tmp_path / ".env").write_text("OBS_PASSWORD=from_env\nOBS_HOST=hostfromenv\n")
    monkeypatch.setattr(ENG, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("OBS_PASSWORD", raising=False)
    monkeypatch.delenv("OBS_HOST", raising=False)
    ENG.load_env()
    import os
    assert os.environ["OBS_PASSWORD"] == "from_local" and os.environ["OBS_HOST"] == "hostfromenv"
