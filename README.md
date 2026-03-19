# KingdomVR Launcher

A Python GUI launcher for the KingdomVR client. On startup it first checks for
a newer launcher release, updates itself if required, then checks GitHub for
the latest KingdomVR release, prompts the user to download and install it if
needed, and finally launches the game.

## Features

- **Auto-update check** – queries the GitHub Releases API on every launch.
- **Launcher self-update (required)** – checks `KingdomVR/launcher` first and
  requires installing the latest launcher before running KingdomVR (Windows
  via installer asset, macOS via zip replacement of the app bundle).
- **First-run install** – prompts the user to download the game if no version
  is present yet.
- **Optional update** – if an update is available the user can choose to
  install it or skip and run the existing version.
- **Progress bar** – shows download progress while fetching the release zip.
- **Platform-specific storage** – Windows uses `%APPDATA%\KingdomVR\`; macOS
  uses `~/Library/Application Support/KingdomVR/`.
- **Cross-platform launcher** – supports Windows and macOS release installs.

## Requirements

- Python 3.10 or newer (uses the built-in `tkinter` for the GUI)
- [`requests`](https://pypi.org/project/requests/)

```
pip install -r requirements.txt
```

## Running

```
python launcher.py
```

## AppData layout

```
%APPDATA%\KingdomVR\
├── config.json            # tracks game + launcher versions
├── downloads\             # temporary zip files (cleaned up after install)
└── versions\
    └── v1.0\              # extracted game files for each installed version
        └── KingdomVR.exe
```

## macOS data layout

```
~/Library/Application Support/KingdomVR/
├── config.json                    # tracks game + launcher versions
├── downloads/                     # temporary zip files (cleaned up after install)
└── versions/
    └── v1.0/                      # extracted game files for each installed version
        └── KingdomVR.app
```

## Release asset naming

The launcher expects release assets to follow platform conventions:

```
KingdomVR-v<major>.<minor>-windows.zip
KingdomVR-v<major>.<minor>-macos.zip
```

For example: `KingdomVR-v1.0-windows.zip` and `KingdomVR-v1.0-macos.zip`

## Configuration

Edit the constants near the top of `launcher.py` to point at a different
GitHub repository or change the expected exe / zip naming:

| Constant | Default | Purpose |
|---|---|---|
| `GITHUB_REPO` | `KingdomVR/KingdomVR` | Owner/repo for release checks |
| `LAUNCHER_GITHUB_REPO` | `KingdomVR/launcher` | Owner/repo for launcher self-updates |
| `LAUNCHER_VERSION` | `1.0.0` | Current launcher version used for self-update comparison |
| `GAME_EXE` | `KingdomVR.exe` | Executable name to launch |
