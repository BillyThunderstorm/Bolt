"""Targeted tests for Bolt_Mac_App (temp folders only; never touches ~/Applications)."""
import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))
import modules.Bolt_Mac_App as m  # noqa: E402


@pytest.fixture
def tmp_apps(tmp_path, monkeypatch):
    dist = tmp_path / "dist" / "Bolt.app"
    inst = tmp_path / "Applications" / "Bolt.app"
    monkeypatch.setattr(m, "_DIST_APP", dist)
    monkeypatch.setattr(m, "_INSTALLED_APP", inst)
    return dist, inst


def _build(dist):
    assert m.try_build() == 0
    assert dist.is_dir()


def test_plist_is_menu_bar_only_and_valid(tmp_apps):
    data = plistlib.loads(m._info_plist_xml().encode())
    assert data["LSUIElement"] is True
    assert data["CFBundleIdentifier"] == m._BUNDLE_ID


def test_launcher_syntax_and_safety(tmp_path):
    script = tmp_path / "Bolt"
    script.write_text(m._launcher_script())
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    text = script.read_text()
    assert "/opt/homebrew/bin" in text          # Finder PATH has no Homebrew
    assert "menubar.log" in text                 # output goes to a log
    assert "pgrep -f" in text                    # never a second icon


def test_build_then_not_stale(tmp_apps):
    dist, _ = tmp_apps
    _build(dist)
    assert m._bundle_looks_valid(dist)
    assert not m._bundle_stale(dist)
    (dist / "Contents" / "MacOS" / "Bolt").write_text("#!/bin/bash\necho old\n")
    assert m._bundle_stale(dist)


def test_install_copies_and_refuses_foreign_app(tmp_apps, capsys):
    dist, inst = tmp_apps
    _build(dist)
    assert m.try_install() == 0
    assert m._bundle_looks_valid(inst)
    assert not m._bundle_stale(inst)
    # A different app with the same name is never overwritten.
    plist = inst / "Contents" / "Info.plist"
    plist.write_text(plist.read_text().replace(m._BUNDLE_ID, "com.example.other"))
    assert m.try_install() == 1
    assert "com.example.other" in plist.read_text()


def test_install_dry_run_writes_nothing(tmp_apps):
    dist, inst = tmp_apps
    assert m.try_install(dry_run=True) == 0
    assert not inst.exists()


def test_status_json_fields(tmp_apps, capsys):
    dist, _ = tmp_apps
    _build(dist)
    capsys.readouterr()
    m.print_status(as_json=True)
    info = json.loads(capsys.readouterr().out)
    for key in ("installed", "installed_stale", "dist_stale", "running", "log"):
        assert key in info
