from setuptools import setup
from pathlib import Path

HERE = Path(__file__).parent
APP = [str(HERE / "launcher.py")]

# py2app options
OPTIONS = {
    # Py2app prefers a .icns icon file. Convert images/kingdomvr.ico -> .icns and
    # place it alongside this file as images/kingdomvr.icns for the icon to work.
    "iconfile": str(HERE / "images" / "kingdomvr.icns"),
    "resources": [str(HERE / "images")],
    "argv_emulation": False,
    "packages": ["requests"],
    "includes": ["tkinter"],
    "plist": {
        "CFBundleName": "kingdomvr",
        "CFBundleDisplayName": "kingdomvr",
        "CFBundleIdentifier": "com.kingdomvr.launcher",
    },
}

setup(
    app=APP,
    name="kingdomvr",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
