from setuptools import setup
from pathlib import Path

HERE = Path(__file__).parent
APP = [str(HERE / "launcher.py")]

# py2app options
OPTIONS = {
    # py2app prefers a .icns icon file. Convert images/kingdomvr.ico -> .icns
    # and place it as images/kingdomvr.icns for the icon to work.
    "iconfile": str(HERE / "images" / "kingdomvr.icns"),
    "resources": [str(HERE / "images")],
    "argv_emulation": False,
    "packages": ["requests", "PIL"],
    "includes": ["tkinter"],
    # Exclude large / unrelated site-packages which py2app's autodetection
    # may pull in (PyInstaller hooks, Qt, numpy/scipy tests, etc.) and which
    # caused the ImportError in your traceback.
    "excludes": [
        "PyInstaller",
        "PySide2",
        "PySide6",
        "PyQt5",
        "PyQt6",
        "numpy",
        "scipy",
        "matplotlib",
    ],
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
