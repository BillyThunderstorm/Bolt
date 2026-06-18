#!/usr/bin/env python3
"""
setup.py — Build Bolt as a standalone macOS .app
===============================================
Usage:
  python3 setup.py py2app

Output:
  dist/Bolt.app

Run locally without building:
  python3 app.py
"""

from setuptools import setup

APP = ["app.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": True,
    "iconfile": None,
    "packages": ["rumps", "dotenv", "requests", "websocket", "twitchio"],
    "includes": [
        "subprocess",
        "webbrowser",
        "pathlib",
        "json",
        "time",
        "os",
        "sys",
    ],
    "plist": {
        "CFBundleName": "Bolt",
        "CFBundleDisplayName": "Bolt",
        "CFBundleIdentifier": "com.thunderstormbilly.bolt",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False,
        "LSUIElement": False,
    },
}

setup(
    app=APP,
    name="Bolt",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
