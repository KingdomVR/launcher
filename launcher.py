#!/usr/bin/env python3
"""KingdomVR Launcher

A GUI launcher that checks for GitHub releases of the KingdomVR game,
downloads and installs them into the user's AppData directory, and launches
the game executable. No administrator privileges are required.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import zipfile
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import ctypes
from ctypes import wintypes

import requests

# ── Configuration ─────────────────────────────────────────────────────────────
GITHUB_REPO = "KingdomVR/KingdomVR"
LAUNCHER_GITHUB_REPO = "KingdomVR/launcher"
GITHUB_API_BASE = "https://api.github.com"

APP_NAME = "KingdomVR"
GAME_EXE = "kingdomvr.exe"
LAUNCHER_VERSION = "1.1"

# All data lives under %APPDATA%\KingdomVR (no admin rights needed)
APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
VERSIONS_DIR = APPDATA_DIR / "versions"
DOWNLOADS_DIR = APPDATA_DIR / "downloads"
CONFIG_FILE = APPDATA_DIR / "config.json"

# Window dimensions
WINDOW_W = 500
WINDOW_H = 340

# Colors used throughout the UI
BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
ACCENT = "#4a90e2"
TEXT_LIGHT = "#e0e0e0"
TEXT_DIM = "#9090a0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Running in normal Python environment
        base_path = Path(__file__).parent
    return base_path / relative_path


def ensure_dirs() -> None:
    """Create the AppData directories if they do not already exist."""
    for d in (APPDATA_DIR, VERSIONS_DIR, DOWNLOADS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Return the persisted launcher config, or a default dict."""
    default_config = {
        "installed_version": None,
        "launcher_version": LAUNCHER_VERSION,
    }

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if not isinstance(data, dict):
                    return default_config.copy()
                data.setdefault("installed_version", None)
                data.setdefault("launcher_version", LAUNCHER_VERSION)
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return default_config.copy()


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


def get_installed_version() -> str | None:
    return load_config().get("installed_version")


def parse_version_tuple(version: str) -> tuple[int, ...]:
    """Return a comparable numeric tuple for tags like v1.2.3 or 1.2."""
    cleaned = version.strip().lstrip("vV")
    parts = [int(p) for p in re.findall(r"\d+", cleaned)]
    return tuple(parts) if parts else (0,)


def is_version_newer(candidate: str, current: str) -> bool:
    return parse_version_tuple(candidate) > parse_version_tuple(current)


def find_game_exe(version_dir: Path) -> Path | None:
    """Search *version_dir* recursively for KingdomVR.exe."""
    for path in version_dir.rglob(GAME_EXE):
        return path
    return None


def get_latest_release(repo: str) -> dict:
    """Fetch the latest release from the GitHub API (raises on failure)."""
    url = f"{GITHUB_API_BASE}/repos/{repo}/releases/latest"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def find_windows_asset(release: dict) -> tuple:
    """Return (asset_name, download_url) for the Windows zip, or (None, None)."""
    for asset in release.get("assets", []):
        name: str = asset.get("name", "")
        if name.startswith("KingdomVR-v") and name.endswith("-windows.zip"):
            return name, asset["browser_download_url"]
    return None, None


def find_launcher_installer_asset(release: dict) -> tuple:
    """Return (asset_name, download_url) for a Windows launcher installer."""
    assets = release.get("assets", [])

    # Prefer common installer naming first, then any .exe, then .msi.
    for asset in assets:
        name = asset.get("name", "")
        lower = name.lower()
        if lower.endswith(".exe") and any(k in lower for k in ("setup", "installer")):
            return name, asset["browser_download_url"]

    for asset in assets:
        name = asset.get("name", "")
        if name.lower().endswith(".exe"):
            return name, asset["browser_download_url"]

    for asset in assets:
        name = asset.get("name", "")
        if name.lower().endswith(".msi"):
            return name, asset["browser_download_url"]

    return None, None


def download_file(url: str, dest: Path, progress_cb) -> None:
    """Stream *url* to *dest*, calling progress_cb(fraction) as bytes arrive."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        progress_cb(downloaded / total)


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


# ── Logo Canvas ───────────────────────────────────────────────────────────────

def build_logo_canvas(parent: tk.Widget) -> tk.Canvas:
    """Display the KingdomVR logo image."""
    canvas = tk.Canvas(
        parent,
        width=WINDOW_W,
        height=160,
        bg=BG_CARD,
        highlightthickness=0,
    )

    # Load and display the logo image
    try:
        logo_path = get_resource_path("images/kingdomvr.ico")
        img = Image.open(logo_path)
        # Resize if needed (keeping aspect ratio)
        img.thumbnail((120, 120), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        
        # Keep a reference to prevent garbage collection
        canvas.image = photo
        
        # Center the image
        cx = WINDOW_W // 2
        canvas.create_image(cx, 60, image=photo)
        
        # "KingdomVR" text below the logo
        canvas.create_text(
            cx, 128,
            text="KingdomVR",
            font=("Arial", 22, "bold"),
            fill=TEXT_LIGHT,
        )
        canvas.create_text(
            cx, 148,
            text="Launcher",
            font=("Arial", 11),
            fill=TEXT_DIM,
        )
    except Exception as e:
        # Fallback: show text if image fails to load
        canvas.create_text(
            WINDOW_W // 2, 80,
            text="KingdomVR\nLauncher",
            font=("Arial", 22, "bold"),
            fill=TEXT_LIGHT,
            justify="center",
        )
    
    return canvas


# ── Main Application ──────────────────────────────────────────────────────────

class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KingdomVR Launcher")
        self.resizable(False, False)
        self.configure(bg=BG_DARK)
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        
        # Set window icon
        try:
            icon_path = get_resource_path("images/kingdomvr.ico")
            self.iconbitmap(str(icon_path))
        except Exception:
            pass  # Silently fail if icon can't be loaded
        
        # Enable dark mode title bar on Windows 10/11
        try:
            import ctypes as ct
            hwnd = ct.windll.user32.GetParent(self.winfo_id())
            value = ct.c_int(2)  # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 11) or 19 (Windows 10 builds)
            # Try Windows 11 attribute first
            ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ct.byref(value), ct.sizeof(value))
        except Exception:
            try:
                # Fall back to Windows 10 builds 19041+
                ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ct.byref(value), ct.sizeof(value))
            except Exception:
                pass  # Not on Windows or older version, just continue
        
        self._center_window()
        self._build_ui()

        ensure_dirs()
        # Start update check on a daemon thread so the GUI stays responsive
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _center_window(self) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{(sw - WINDOW_W) // 2}+{(sh - WINDOW_H) // 2}")

    def _build_ui(self) -> None:
        # Logo area
        logo = build_logo_canvas(self)
        logo.pack(fill="x")

        # Status area
        status_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=8)
        status_frame.pack(fill="both", expand=True)

        self._status_var = tk.StringVar(value="Starting up…")
        tk.Label(
            status_frame,
            textvariable=self._status_var,
            font=("Arial", 10),
            fg=TEXT_LIGHT,
            bg=BG_DARK,
            anchor="w",
            wraplength=WINDOW_W - 40,
            justify="left",
        ).pack(fill="x")

        self._progress = ttk.Progressbar(
            status_frame, mode="indeterminate", length=WINDOW_W - 40
        )
        self._progress.pack(fill="x", pady=(6, 0))
        self._progress.start(10)

        # Bottom button row
        btn_frame = tk.Frame(self, bg=BG_DARK, padx=20, pady=12)
        btn_frame.pack(fill="x", side="bottom")

        self._version_label = tk.Label(
            btn_frame, text="", font=("Arial", 9), fg=TEXT_DIM, bg=BG_DARK
        )

        # Version label and About link inline (show KingdomVR version and About)
        self._version_label.pack(side="left")

        sep = tk.Label(btn_frame, text=" | ", font=("Arial", 9), fg=TEXT_DIM, bg=BG_DARK)
        sep.pack(side="left", padx=(6, 0))

        self._about_link = tk.Label(
            btn_frame,
            text="About",
            font=("Arial", 9, "underline"),
            fg=ACCENT,
            bg=BG_DARK,
            cursor="hand2",
        )
        self._about_link.pack(side="left")
        self._about_link.bind("<Button-1>", lambda e: self._open_about())

        self._launch_btn = tk.Button(
            btn_frame,
            text="Launch",
            state="disabled",
            font=("Arial", 12, "bold"),
            bg=ACCENT,
            fg="white",
            activebackground="#3a7bc2",
            activeforeground="white",
            relief="flat",
            padx=20,
            pady=6,
            cursor="hand2",
            command=self._launch_game,
        )
        self._launch_btn.pack(side="right")

    # ── Thread-safe UI helpers ────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_var.set(text))

    def _set_version_label(self, text: str) -> None:
        self.after(0, lambda: self._version_label.configure(text=text))

    def _stop_progress(self) -> None:
        def _do():
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)
        self.after(0, _do)

    def _set_progress(self, fraction: float) -> None:
        """Update progress bar (0.0 – 1.0) from any thread."""
        def _do():
            self._progress.configure(mode="determinate")
            self._progress["value"] = fraction * 100
        self.after(0, _do)

    def _enable_launch(self) -> None:
        self.after(0, lambda: self._launch_btn.configure(state="normal"))

    # ── Dialogs (must run on the main thread) ─────────────────────────────────

    def _ask(self, title: str, message: str) -> bool:
        """Show a yes/no dialog from a background thread and return the answer."""
        result: dict = {"value": False}
        done = threading.Event()

        def _show():
            result["value"] = messagebox.askyesno(title, message, parent=self)
            done.set()

        self.after(0, _show)
        done.wait()
        return result["value"]

    def _show_error(self, title: str, message: str) -> None:
        self.after(0, lambda: messagebox.showerror(title, message, parent=self))

    # ── Update-check logic (runs on background thread) ────────────────────────

    def _check_for_updates(self) -> None:
        if self._handle_launcher_self_update():
            return

        installed = get_installed_version()

        try:
            self._set_status("Checking for KingdomVR updates…")
            release = get_latest_release(GITHUB_REPO)
        except (requests.RequestException, OSError) as exc:  # network / HTTP errors
            self._stop_progress()
            if installed:
                self._set_status(
                    f"Could not check for updates ({exc}).\n"
                    "You can still launch the installed version."
                )
                self._set_version_label(f"Installed: {installed}")
                self._enable_launch()
            else:
                self._set_status("No internet connection and nothing installed.")
                self._show_error(
                    "Cannot Connect",
                    "Could not reach GitHub to check for updates and no version is "
                    "installed.\n\nPlease check your internet connection and try again.",
                )
                self.after(0, self.destroy)
            return

        latest_tag: str = release.get("tag_name", "")
        asset_name, download_url = find_windows_asset(release)

        if not download_url:
            self._stop_progress()
            if installed:
                self._set_status(
                    "No Windows release asset found on GitHub. "
                    "Launching the installed version."
                )
                self._set_version_label(f"Installed: {installed}")
                self._enable_launch()
            else:
                self._show_error(
                    "No Asset Found",
                    "The latest GitHub release has no Windows zip. Cannot install.",
                )
                self.after(0, self.destroy)
            return

        if installed is None:
            # First run — force install
            self._stop_progress()
            self._set_status(f"No installation found. Latest version available: {latest_tag}")
            if self._ask(
                "Install KingdomVR",
                f"KingdomVR is not installed yet.\n\n"
                f"Would you like to download and install version {latest_tag} now?",
            ):
                self._download_and_install(latest_tag, download_url, asset_name)
            else:
                self.after(0, self.destroy)
            return

        if installed == latest_tag:
            self._stop_progress()
            self._set_status("You are up to date. Ready to launch!")
            self._set_version_label(f"Version: {installed}")
            self._enable_launch()
            return

        # A newer version is available
        self._stop_progress()
        self._set_status(
            f"Update available: {latest_tag}  (installed: {installed})"
        )
        if self._ask(
            "Update Available",
            f"A new version of KingdomVR is available!\n\n"
            f"Installed : {installed}\n"
            f"Latest    : {latest_tag}\n\n"
            "Download and install the update?",
        ):
            self._download_and_install(latest_tag, download_url, asset_name)
        else:
            self._set_status(f"Skipping update. Running version {installed}.")
            self._set_version_label(f"Version: {installed}")
            self._enable_launch()

    def _handle_launcher_self_update(self) -> bool:
        """Return True if self-update flow took over and app should stop normal flow."""
        self._set_status("Checking launcher updates…")

        # Ensure the running launcher version is tracked in config.
        cfg = load_config()
        if cfg.get("launcher_version") != LAUNCHER_VERSION:
            cfg["launcher_version"] = LAUNCHER_VERSION
            save_config(cfg)

        try:
            launcher_release = get_latest_release(LAUNCHER_GITHUB_REPO)
        except (requests.RequestException, OSError):
            # If the launcher version cannot be checked, continue with game checks.
            return False

        latest_launcher_tag = (launcher_release.get("tag_name") or "").strip()
        if not latest_launcher_tag:
            return False

        if not is_version_newer(latest_launcher_tag, LAUNCHER_VERSION):
            return False

        installer_name, installer_url = find_launcher_installer_asset(launcher_release)
        if not installer_url:
            self._stop_progress()
            self._show_error(
                "Launcher Update Required",
                "A newer launcher version is available, but no Windows installer "
                "asset was found in the latest launcher release.\n\n"
                "Please download the newest launcher manually from "
                "https://github.com/KingdomVR/launcher/releases/latest",
            )
            self.after(0, self.destroy)
            return True

        self._stop_progress()
        proceed = self._ask(
            "Launcher Update Required",
            "A new KingdomVR Launcher version is available and must be installed "
            "before launching KingdomVR.\n\n"
            f"Current launcher: {LAUNCHER_VERSION}\n"
            f"Required launcher: {latest_launcher_tag}\n\n"
            "Download and run the new launcher installer now?",
        )
        if not proceed:
            self.after(0, self.destroy)
            return True

        self._download_and_run_launcher_installer(
            latest_launcher_tag,
            installer_url,
            installer_name,
        )
        return True

    def _download_and_run_launcher_installer(self, tag: str, url: str, asset_name: str) -> None:
        temp_dir = Path(tempfile.gettempdir()) / "KingdomVRLauncher" / "updates"
        installer_dest = temp_dir / asset_name

        try:
            self._set_status("Preparing launcher update download…")
            self.after(0, lambda: self._progress.configure(mode="indeterminate"))
            self.after(0, lambda: self._progress.start(10))

            first_byte = threading.Event()

            def _progress_cb(fraction: float) -> None:
                if not first_byte.is_set():
                    first_byte.set()
                    self.after(0, lambda: self._progress.stop())
                self._set_progress(fraction)
                self._set_status(f"Downloading launcher update {asset_name}… {int(fraction * 100)}%")

            download_file(url, installer_dest, _progress_cb)

            self._set_status(f"Opening launcher installer {tag}…")
            self._launch_detached(installer_dest)
            self.after(0, self.destroy)
        except (requests.RequestException, OSError, ValueError) as exc:
            self._stop_progress()
            self._show_error(
                "Launcher Update Failed",
                "Failed to download or launch the new launcher installer.\n\n"
                f"{exc}",
            )
            self.after(0, self.destroy)

    def _launch_detached(self, executable_path: Path) -> None:
        subprocess.Popen(
            [str(executable_path)],
            cwd=str(executable_path.parent),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Download / install (runs on background thread) ────────────────────────

    def _download_and_install(self, tag: str, url: str, asset_name: str) -> None:
        zip_dest = DOWNLOADS_DIR / asset_name

        try:
            # --- Download phase ---
            self._set_status(f"Connecting to download server…")
            # Switch to indeterminate while we wait for headers
            self.after(0, lambda: self._progress.configure(mode="indeterminate"))
            self.after(0, lambda: self._progress.start(10))

            first_byte = threading.Event()

            def _progress_cb(fraction: float) -> None:
                if not first_byte.is_set():
                    first_byte.set()
                    # Switch to determinate now that we know the size
                    self.after(0, lambda: self._progress.stop())
                self._set_progress(fraction)
                pct = int(fraction * 100)
                self._set_status(f"Downloading {asset_name}… {pct}%")

            download_file(url, zip_dest, _progress_cb)

            # --- Extract phase ---
            self._set_status(f"Extracting {asset_name}…")
            self.after(0, lambda: self._progress.configure(mode="indeterminate"))
            self.after(0, lambda: self._progress.start(10))

            version_dir = VERSIONS_DIR / tag
            extract_zip(zip_dest, version_dir)

            # Clean up the downloaded zip
            try:
                zip_dest.unlink()
            except OSError:
                pass

            # Persist the new installed version
            cfg = load_config()
            cfg["installed_version"] = tag
            save_config(cfg)

            self._stop_progress()
            self._set_status(f"KingdomVR {tag} installed successfully. Ready to launch!")
            self._set_version_label(f"Version: {tag}")
            self._enable_launch()

        except (requests.RequestException, zipfile.BadZipFile, OSError, ValueError) as exc:
            self._stop_progress()
            self._set_status(f"Installation failed: {exc}")
            self._show_error("Installation Failed", str(exc))

            installed = get_installed_version()
            if installed:
                self._set_status(
                    f"Installation failed. You can still launch version {installed}."
                )
                self._set_version_label(f"Version: {installed}")
                self._enable_launch()
            else:
                self.after(0, self.destroy)

    # ── Launch ────────────────────────────────────────────────────────────────

    def _launch_game(self) -> None:
        installed = get_installed_version()
        if not installed:
            messagebox.showerror("Error", "No version is installed.", parent=self)
            return

        version_dir = VERSIONS_DIR / installed
        
        if not version_dir.exists():
            messagebox.showerror(
                "Directory Not Found",
                f"Version directory does not exist:\n{version_dir}\n\n"
                "The installation may be corrupted. Please re-launch to repair.",
                parent=self,
            )
            return
        
        exe_path = find_game_exe(version_dir)

        if exe_path is None or not exe_path.exists():
            messagebox.showerror(
                "Executable Not Found",
                f"Could not find {GAME_EXE} in:\n{version_dir}\n\n"
                "The installation may be corrupted. Please re-launch to repair.",
                parent=self,
            )
            return

        # Ensure the resolved path stays within VERSIONS_DIR (prevent path traversal
        # in case config.json is modified maliciously).
        try:
            exe_path.resolve().relative_to(VERSIONS_DIR.resolve())
        except ValueError:
            messagebox.showerror(
                "Security Error",
                "The game executable path is outside the expected install directory.\n"
                "Please re-install KingdomVR.",
                parent=self,
            )
            return

        try:
            self._launch_detached(exe_path)
        except Exception as e:
            messagebox.showerror(
                "Launch Failed",
                f"Failed to launch game:\n{e}",
                parent=self,
            )
            return
            
        self.destroy()

    # ── About / Vehicles Fix ─────────────────────────────────────────────────

    def _open_about(self) -> None:
        """Open a small About window with versions and the vehicles-fix action."""
        installed = get_installed_version() or "(not installed)"

        about = tk.Toplevel(self)
        about.title("About")
        about.resizable(False, False)
        about.configure(bg=BG_DARK)

        # Set same icon as main window so the Toplevel shows the correct mini-icon
        try:
            icon_path = get_resource_path("images/kingdomvr.ico")
            about.iconbitmap(str(icon_path))
        except Exception:
            pass

        # Try to enable immersive dark title bar on Windows for the about window too
        try:
            import ctypes as ct
            hwnd = ct.windll.user32.GetParent(about.winfo_id())
            value = ct.c_int(2)
            try:
                ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ct.byref(value), ct.sizeof(value))
            except Exception:
                try:
                    ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ct.byref(value), ct.sizeof(value))
                except Exception:
                    pass
        except Exception:
            pass

        pad = dict(padx=14, pady=8)
        tk.Label(
            about,
            text=f"Launcher version: {LAUNCHER_VERSION}",
            fg=TEXT_LIGHT,
            bg=BG_DARK,
            font=("Arial", 10, "bold"),
        ).pack(**pad)

        tk.Label(
            about,
            text=f"Installed KingdomVR: {installed}",
            fg=TEXT_LIGHT,
            bg=BG_DARK,
            font=("Arial", 10),
        ).pack(**pad)

        btn = tk.Button(
            about,
            text="Apply vehicles fix",
            font=("Arial", 10),
            bg=ACCENT,
            fg="white",
            activebackground="#3a7bc2",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: threading.Thread(target=self._apply_vehicles_fix, args=(about,), daemon=True).start(),
        )
        btn.pack(pady=(6, 12))

    def _apply_vehicles_fix(self, parent_window: tk.Widget | None = None) -> None:
        """Download vehicles.zip, extract, and move .bmesh/.basis into Cyberspace resources."""
        url = "https://github.com/KingdomVR/vehicles/releases/download/v1.0/vehicles.zip"

        try:
            self._set_status("Downloading vehicles fix…")

            temp_dir = Path(tempfile.gettempdir()) / "KingdomVR" / "vehicles_fix"
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            temp_dir.mkdir(parents=True, exist_ok=True)

            zip_dest = temp_dir / "vehicles.zip"

            def _progress_cb(fraction: float) -> None:
                # update a lightweight progress indicator
                try:
                    self._set_progress(fraction)
                except Exception:
                    pass

            download_file(url, zip_dest, _progress_cb)

            self._set_status("Extracting vehicles fix…")
            extract_dir = temp_dir / "extracted"
            extract_zip(zip_dest, extract_dir)

            dest_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Cyberspace" / "resources"
            dest_dir.mkdir(parents=True, exist_ok=True)

            moved = 0
            for p in extract_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".bmesh", ".basis"):
                    dest = dest_dir / p.name
                    try:
                        shutil.copy2(p, dest)
                        moved += 1
                    except Exception as ex:
                        # attempt to replace using os.replace as a fallback
                        try:
                            tmp = dest.with_suffix(dest.suffix + ".tmp")
                            shutil.copy2(p, tmp)
                            os.replace(tmp, dest)
                            moved += 1
                        except Exception:
                            raise ex

            # Clean up temp
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

            messagebox.showinfo("Vehicles Fix", f"Vehicles fix applied. {moved} files updated.", parent=self)
            self._set_status("Vehicles fix applied.")

        except Exception as exc:
            self._stop_progress()
            self._show_error("Vehicles Fix Failed", str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Fix Windows taskbar icon BEFORE creating any windows
    if sys.platform == "win32":
        try:
            # Set a unique AppUserModelID so Windows doesn't group with Python
            myappid = 'kingdomvr.launcher.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    
    if sys.platform != "win32":
        # Warn but still allow running (useful for development on other platforms)
        print(
            "Warning: KingdomVR Launcher is designed for Windows. "
            "Some features may not work correctly on this platform.",
            file=sys.stderr,
        )
    app = LauncherApp()
    app.mainloop()
