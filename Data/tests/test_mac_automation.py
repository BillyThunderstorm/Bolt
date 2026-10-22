"""Targeted tests for Mac_Automation (bolt mac-auto). Temp files + mocks only:
never reads or writes the real crontab, launchd or Shortcuts."""
import os
import plistlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Core"))
sys.path.insert(0, str(ROOT / "scripts"))
from modules import Mac_Automation as ma  # noqa: E402

NOW = datetime(2026, 10, 20, 19, 40)  # Tue


def _sched(expr):
    return ma.parse_schedule(expr.split())


def test_describe_schedules():
    assert ma.describe_schedule("*/30 * * * *".split()) == "every 30 minutes"
    assert ma.describe_schedule("0 */3 * * *".split()) == "every 3 hours on the hour"
    assert ma.describe_schedule("10 */2 * * *".split()) == "every 2 hours at :10"
    assert ma.describe_schedule("0 3 * * *".split()) == "daily at 3 AM"
    assert ma.describe_schedule("0 17 * * *".split()) == "daily at 5 PM"
    assert ma.describe_schedule("0 9 * * 0".split()) == "Sundays at 9 AM"


def test_previous_runs():
    assert ma.previous_runs(_sched("10 */2 * * *"), NOW) == [datetime(2026, 10, 20, 18, 10),
                                                              datetime(2026, 10, 20, 16, 10)]
    # Sunday 9 AM → Sun Oct 18
    assert ma.previous_runs(_sched("0 9 * * 0"), NOW, count=1) == [datetime(2026, 10, 18, 9, 0)]
    assert ma.parse_schedule("61 * * * *".split()) is None


def test_parse_crontab_skips_comments_and_env():
    text = "# hi\nSHELL=/bin/bash\n# Daily at 5pm\n0 17 * * * echo hi >> /tmp/x.log 2>&1\n\n@reboot echo up\nbad line\n"
    rows = ma.parse_crontab(text)
    assert [r["special"] for r in rows] == [None, "@reboot", "invalid"]
    assert rows[0]["comment"] == "Daily at 5pm"
    assert rows[0]["command"].startswith("echo hi")


def test_split_command_logs_and_segments(tmp_path):
    segs, logs = ma._split_command(f"cd {tmp_path} && ./a.sh --x >> {tmp_path}/a.log 2>&1")
    assert segs == [["cd", str(tmp_path)], ["./a.sh", "--x"]]
    assert logs == [f"{tmp_path}/a.log"]


def test_check_targets_missing_not_exec_ok(tmp_path):
    ok = tmp_path / "ok.sh"
    ok.write_text("#!/bin/bash\necho ok\n")
    ok.chmod(0o755)
    noexec = tmp_path / "noexec.sh"
    noexec.write_text("#!/bin/bash\necho\n")
    noexec.chmod(0o644)
    assert ma.check_targets(f"cd {tmp_path} && ./ok.sh")["problems"] == []
    p = ma.check_targets(f"cd {tmp_path} && ./noexec.sh")["problems"]
    assert p and p[0]["kind"] == "BROKEN" and "chmod +x" in p[0]["fix"]
    p = ma.check_targets(f"cd {tmp_path} && ./gone.sh")["problems"]
    assert p and "missing" in p[0]["detail"]
    py = tmp_path / "python3"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    (tmp_path / "job.py").write_text("print('x')\n")
    assert ma.check_targets(f"cd {tmp_path} && {py} job.py --send")["problems"] == []
    (tmp_path / "bad.py").write_text("def (:\n")
    p = ma.check_targets(f"cd {tmp_path} && {py} bad.py")["problems"]
    assert p and "syntax" in p[0]["detail"].lower()
    p = ma.check_targets(f"cd {tmp_path} && {py} nope.py")["problems"]
    assert p and "nope.py" in p[0]["detail"]


def test_last_error_rules():
    assert ma._last_error(["Wrote site data", "Sites unavailable: git push failed: x"]).startswith("Sites")
    assert ma._last_error(["Traceback (most recent call last):", "x", "Storage monitor completed"]) is None
    assert ma._last_error(["Failed: 0", "Total videos inspected: 2"]) is None
    assert ma._last_error(["\x1b[31mERROR\x1b[0m boom"]) == "ERROR boom"


def _set_mtime(p, dt):
    ts = dt.timestamp()
    os.utime(p, (ts, ts))


def _job(tmp_path, sched, script="storage_monitor.sh"):
    s = tmp_path / script
    s.write_text("#!/bin/bash\necho\n")
    s.chmod(0o755)
    log = tmp_path / "job.log"
    entry = ma.parse_crontab(f"{sched} cd {tmp_path} && ./{script} >> {log} 2>&1")[0]
    return entry, log


def test_cron_job_on_time_stale_late_failing(tmp_path):
    entry, log = _job(tmp_path, "0 */3 * * *")
    log.write_text("Storage monitor completed\n")
    _set_mtime(log, datetime(2026, 10, 20, 18, 0, 1))
    j = ma.check_cron_job(entry, NOW)
    assert j["state"] == "OK" and j["freshness"] == "on time" and j["name"] == "Storage monitor"
    _set_mtime(log, datetime(2026, 10, 20, 15, 0, 1))  # missed 18:00 only
    assert ma.check_cron_job(entry, NOW)["state"] == "LATE"
    _set_mtime(log, datetime(2026, 10, 19, 9, 0))
    j = ma.check_cron_job(entry, NOW)
    assert j["state"] == "STALE" and j["problems"][0]["fix"]
    log.write_text("start\nERROR: disk read failed\n")
    _set_mtime(log, datetime(2026, 10, 20, 18, 0, 1))
    j = ma.check_cron_job(entry, NOW)
    assert j["state"] == "FAILING" and "disk read failed" in j["problems"][0]["detail"]


def test_quiet_job_uses_heartbeat(tmp_path, monkeypatch):
    entry, log = _job(tmp_path, "*/30 * * * *", script="compress_videos.sh")
    log.write_text("Video compression scan completed\n")
    _set_mtime(log, NOW - timedelta(hours=14))
    monkeypatch.setattr(ma, "_HEARTBEAT_DIR", tmp_path / "hb")
    assert ma.check_cron_job(entry, NOW)["freshness"] == "quiet"
    (tmp_path / "hb").mkdir()
    hb = tmp_path / "hb" / "compress_videos.last"
    hb.write_text("x")
    _set_mtime(hb, datetime(2026, 10, 20, 19, 30, 0))
    j = ma.check_cron_job(entry, NOW)
    assert j["freshness"] == "on time" and j["state"] == "OK"
    _set_mtime(hb, NOW - timedelta(hours=5))
    assert ma.check_cron_job(entry, NOW)["state"] == "STALE"


def test_duplicate_failing_lines_reported_once(tmp_path, monkeypatch):
    s = tmp_path / "site_data_writer.py"
    s.write_text("print(1)\n")
    py = tmp_path / "python3"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    log = tmp_path / "cron.log"
    log.write_text("Wrote\n  Sites unavailable: git push failed: boom\n")
    push = tmp_path / "logs" / "site_data_push.log"
    push.parent.mkdir()
    push.write_text("[2026-10-20 18:10:03 CT] Sites unavailable: git push failed: boom\n")
    monkeypatch.setattr(ma, "_REPO", tmp_path)
    entry = ma.parse_crontab(f"10 */2 * * * cd {tmp_path} && {py} site_data_writer.py --push >> {log} 2>&1")[0]
    j = ma.check_cron_job(entry, NOW)
    assert j["state"] == "FAILING"
    assert len([p for p in j["problems"] if p["kind"] == "FAILING"]) == 1


def test_osascript_typo_flagged(tmp_path):
    if sys.platform != "darwin":
        return
    s = tmp_path / "hour.sh"
    s.write_text("#!/bin/bash\n/usr/bin/osascript -e 'display notification \"a\" with title \"b\" body \"c\"'\n")
    s.chmod(0o755)
    p = ma.check_targets(f"{s}")["problems"]
    assert p and "subtitle" in p[0]["detail"]
    s.write_text("#!/bin/bash\n/usr/bin/osascript -e 'display notification \"a\" with title \"b\" subtitle \"c\"'\n")
    assert ma.check_targets(f"{s}")["problems"] == []


def _plist(tmp_path, prog):
    p = tmp_path / "x.plist"
    (tmp_path / "launch.py").write_text("print(1)\n")
    with open(p, "wb") as fh:
        plistlib.dump({"Label": "x", "ProgramArguments": [str(prog), str(tmp_path / "launch.py"), "live"],
                       "WorkingDirectory": str(tmp_path),
                       "StandardOutPath": str(tmp_path / "out.log"),
                       "StandardErrorPath": str(tmp_path / "err.log")}, fh)
    return p


def test_launchd_running_and_not_loaded(tmp_path):
    py = tmp_path / "python3"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    plist = _plist(tmp_path, py)
    with mock.patch.object(ma, "_launchctl_entry", return_value=({"pid": 42, "last_exit": 0}, None)), \
         mock.patch.object(ma, "_proc_uptime", return_value="01:00"):
        j = ma.check_launchd(plist, "x", NOW)
    assert j["state"] == "OK" and j["running"] and "PID 42" in j["running_words"]
    with mock.patch.object(ma, "_launchctl_entry", return_value=({}, None)):
        j = ma.check_launchd(plist, "x", NOW)
    assert j["state"] == "FAILING" and "launchctl load" in j["problems"][0]["fix"]
    py.unlink()
    with mock.patch.object(ma, "_launchctl_entry", return_value=({"pid": 42, "last_exit": 0}, None)), \
         mock.patch.object(ma, "_proc_uptime", return_value=None):
        assert ma.check_launchd(plist, "x", NOW)["state"] == "BROKEN"
    assert ma.check_launchd(tmp_path / "none.plist", "x", NOW) is None


def test_shortcuts_matching_underscores():
    lib = ["Bolt_Morning", "Bolt_Review_Queue", "Bolt_Stats", "Bolt_Wrap-Up",
           "Extract_Text_from_Photos", "Extract_Text_from_JPGs_to_PDF", "Make GIF"]
    j = ma.check_shortcuts(lib, None)
    assert j["missing"] == [] and len(j["found"]) == 6
    j = ma.check_shortcuts(lib[:2], None)
    assert "Bolt Stats" in j["missing"]
    assert any(p["kind"] == "MISSING" for p in j["problems"])
    j = ma.check_shortcuts(None, "shortcuts list timed out")
    assert "timed out" in j["summary"]


def test_plan_cron_never_duplicates_and_apply_backs_up(tmp_path):
    full = "\n".join(d["comment"] + "\n" + d["line"] for d in ma.desired_cron_entries())
    assert ma.plan_cron(full) == []
    # commented-out line doesn't count as installed
    text = "# 0 17 * * * python daily_briefing.py --send\n0 * * * * echo keep\n"
    missing = ma.plan_cron(text)
    assert len(missing) == 2
    written = {}
    r = ma.apply_cron(text, missing, backup_dir=tmp_path / "bk", writer=lambda b: written.setdefault("b", b))
    assert r["changed"] and Path(r["backup"]).read_text() == text
    assert "0 * * * * echo keep" in written["b"]
    assert ma.plan_cron(written["b"]) == []
    assert ma.apply_cron(written["b"], [], backup_dir=tmp_path / "bk")["changed"] is False


def test_install_is_dry_run_by_default(capsys):
    with mock.patch.object(ma.platform, "system", return_value="Darwin"), \
         mock.patch.object(ma, "_crontab_text", return_value=("0 * * * * echo\n", None)), \
         mock.patch.object(ma, "apply_cron") as ap:
        ma.main(["install", "cron"])
        ma.main(["install", "cron", "--apply", "--dry-run"])
        assert not ap.called
        out = capsys.readouterr().out
        assert "dry run" in out and "would add" in out
        ma.main(["install", "cron", "--apply"])
        assert ap.called


def test_status_never_raises_and_reports_ready():
    with mock.patch.object(ma, "collect", side_effect=RuntimeError("boom")):
        s = ma.status()
    assert s["ready"] is False and s["error"].startswith("Mac automation unavailable:")
    fake = {"jobs": [{"kind": "cron", "name": "A", "bolt": True, "state": "OK", "line": "x daily_briefing.py"},
                     {"kind": "cron", "name": "B", "bolt": True, "state": "FAILING", "line": "y",
                      "problems": [{"kind": "FAILING", "detail": "d", "fix": "f"}]}],
            "crontab_error": None, "crontab_readable": True}
    with mock.patch.object(ma, "collect", return_value=fake), \
         mock.patch.object(ma.platform, "system", return_value="Darwin"):
        s = ma.status(probe=True)
    assert s["ready"] and not s["healthy"] and s["readiness"] == "READY"
    assert s["needs_attention"][0]["name"] == "B" and "B: FAILING" in s["hint"]
    assert s["probe_ok"] is False


def test_site_data_git_env_adds_homebrew():
    import site_data_writer as w
    env = w._git_env({"PATH": "/usr/bin:/bin", "GIT_INDEX_FILE": "/tmp/i"})
    assert env["GIT_INDEX_FILE"] == "/tmp/i"
    if os.path.isdir("/opt/homebrew/bin"):
        assert env["PATH"].split(":")[0] == "/opt/homebrew/bin"
    assert env["PATH"].endswith("/usr/bin:/bin")
