"""
resolver.py — System Resolver Layer

Sits between intent detection and command generation.
Resolves app names, verifies paths, checks installed software
so the AI never has to guess what's actually on the system.
"""

import os
import subprocess
import json
import glob
import re

# Data files live at the project root (one level up from this package),
# not inside the installed package itself.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(PROJECT_ROOT, "app_cache.json")

# Common plain-English names mapped to possible binaries (in order of preference)
APP_ALIASES = {
    "calculator":    ["gnome-calculator", "kcalc", "mate-calc", "xcalc", "qalculate-gtk"],
    "browser":       ["firefox", "chromium", "google-chrome", "brave-browser", "opera"],
    "firefox":       ["firefox"],
    "chrome":        ["google-chrome", "chromium"],
    "brave":         ["brave-browser"],
    "terminal":      ["gnome-terminal", "konsole", "xterm", "mate-terminal", "tilix"],
    "files":         ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"],
    "file manager":  ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"],
    "text editor":   ["gedit", "kate", "mousepad", "pluma", "xed"],
    "editor":        ["gedit", "kate", "mousepad", "pluma", "xed"],
    "music":         ["rhythmbox", "amarok", "clementine", "vlc"],
    "music player":  ["rhythmbox", "amarok", "clementine", "vlc"],
    "video":         ["vlc", "totem", "mpv"],
    "video player":  ["vlc", "totem", "mpv"],
    "image viewer":  ["eog", "gwenview", "ristretto", "shotwell", "xviewer"],
    "photos":        ["shotwell", "eog", "gwenview"],
    "steam":         ["steam"],
    "discord":       ["discord"],
    "vscode":        ["code"],
    "vs code":       ["code"],
    "code":          ["code"],
    "settings":      ["gnome-control-center", "mate-control-center", "systemsettings5"],
    "system monitor":["gnome-system-monitor", "mate-system-monitor", "ksysguard"],
    "screenshot":    ["flameshot", "gnome-screenshot", "mate-screenshot"],
    "archive":       ["file-roller", "ark", "xarchiver"],
    "pdf":           ["evince", "okular", "atril"],
    "office":        ["libreoffice", "onlyoffice-desktopeditors"],
    "writer":        ["libreoffice --writer"],
    "spreadsheet":   ["libreoffice --calc"],
    "gimp":          ["gimp"],
    "inkscape":      ["inkscape"],
    "blender":       ["blender"],
    "obs":           ["obs"],
    "slack":         ["slack"],
    "zoom":          ["zoom"],
    "telegram":      ["telegram-desktop"],
    "vlc":           ["vlc"],
    "mpv":           ["mpv"],
    "htop":          ["htop"],
    "vim":           ["vim"],
    "nvim":          ["nvim"],
    "nano":          ["nano"],
}


def which(cmd):
    """Check if a command/binary exists on the system."""
    result = subprocess.run(
        ["which", cmd.split()[0]],  # handle "libreoffice --writer" etc
        capture_output=True, text=True
    )
    return result.returncode == 0


def scan_desktop_files():
    """
    Scan ALL installed apps from every possible location.
    Covers apt, flatpak, snap, manual installs, and PATH binaries.
    """
    apps = {}
    patterns = [
        "/usr/share/applications/*.desktop",
        os.path.expanduser("~/.local/share/applications/*.desktop"),
        "/var/lib/flatpak/exports/share/applications/*.desktop",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications/*.desktop"),
        "/var/lib/snapd/desktop/applications/*.desktop",
        "/usr/local/share/applications/*.desktop",
        "/usr/share/kde4/applications/*.desktop",
    ]

    for pattern in patterns:
        for filepath in glob.glob(pattern):
            try:
                name = None
                exec_cmd = None
                is_flatpak = False
                no_display = False

                with open(filepath, "r", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Name=") and name is None:
                            name = line[5:].lower().strip()
                        elif line == "NoDisplay=true":
                            no_display = True
                        elif line.startswith("Exec=") and exec_cmd is None:
                            raw_exec = line[5:].strip()
                            if "flatpak run" in raw_exec:
                                is_flatpak = True
                                matches = re.findall(
                                    r'\b([a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*){2,})\b',
                                    raw_exec
                                )
                                if matches:
                                    exec_cmd = f"flatpak run {matches[-1]}"
                            else:
                                clean = re.sub(r'%[uUfFdDnNickvm]', '', raw_exec).strip()
                                exec_cmd = clean.split()[0] if clean else None

                if no_display:
                    continue

                if name and exec_cmd:
                    if is_flatpak:
                        apps[name] = exec_cmd
                    elif exec_cmd.startswith("/") and os.path.isfile(exec_cmd):
                        apps[name] = exec_cmd
                    elif which(exec_cmd):
                        apps[name] = exec_cmd
            except Exception:
                continue

    # Also scan PATH binary locations directly
    # Catches manual installs, AppImages, scripts in ~/bin etc.
    bin_paths = [
        "/usr/local/bin",
        os.path.expanduser("~/bin"),
        os.path.expanduser("~/.local/bin"),
    ]
    skip_prefixes = ("lib", "python", "perl", "ruby", "pkg", "x86",
                     "dpkg", "apt", "systemd", "dbus", "udev", "gtk", "glib")

    for bin_path in bin_paths:
        if not os.path.isdir(bin_path):
            continue
        try:
            for entry in os.scandir(bin_path):
                if entry.is_file() and os.access(entry.path, os.X_OK):
                    name = entry.name.lower()
                    if not any(name.startswith(p) for p in skip_prefixes):
                        if name not in apps:
                            apps[name] = entry.path
        except Exception:
            continue

    # Termio's own global launcher must never be a resolvable "app" — any
    # request that merely mentions the word "termio" (extremely likely,
    # since the user is talking *to* Termio) would otherwise risk matching
    # it and relaunching the app inside itself.
    apps.pop("termio", None)

    return apps


def build_cache(silent=False):
    """Build the app cache from installed desktop files."""
    if not silent:
        print("  Scanning installed applications...")
    apps = scan_desktop_files()
    with open(CACHE_FILE, "w") as f:
        json.dump(apps, f, indent=2)
    if not silent:
        print(f"  Found {len(apps)} installed apps.")
    return apps


def load_cache():
    """Load app cache, build it if it doesn't exist yet."""
    if not os.path.exists(CACHE_FILE):
        return build_cache()
    with open(CACHE_FILE, "r") as f:
        return json.load(f)


def resolve_app(user_text):
    """
    Try to resolve a plain-English app name to an installed binary.
    Returns binary string if found, None if not.

    If not found in cache, automatically rescans once in case
    the app was recently installed.
    """
    text = user_text.lower().strip()

    # Check alias map first (most reliable, no disk needed)
    # Use word boundaries so e.g. "code" doesn't match inside "zip code"
    for alias, candidates in APP_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', text):
            for candidate in candidates:
                if which(candidate):
                    return candidate

    # Check desktop file cache
    result = _resolve_from_cache(text, load_cache())
    if result:
        return result

    # Not found — rescan silently in case it was recently installed
    fresh_cache = build_cache(silent=True)
    result = _resolve_from_cache(text, fresh_cache)
    return result


def _resolve_from_cache(text, cache):
    """Look up app in a given cache dict. Returns binary or None."""
    # Exact match
    if text in cache:
        cmd = cache[text]
        if cmd.startswith("flatpak run") or which(cmd):
            return cmd

    # Partial match — text is part of an app name
    for app_name, cmd in cache.items():
        if text in app_name:
            if cmd.startswith("flatpak run") or which(cmd):
                return cmd

    # Partial match — app name is part of text
    for app_name, cmd in cache.items():
        if app_name in text:
            if cmd.startswith("flatpak run") or which(cmd):
                return cmd

    return None


def refresh_cache():
    """Public function to force a full rescan. Called after installs."""
    return build_cache(silent=True)


def verify_path(path):
    """
    Check if a path exists. If not, try a case-insensitive fuzzy search.
    Returns (actual_path, found).
    """
    expanded = os.path.expanduser(path)

    if os.path.exists(expanded):
        return expanded, True

    # Try case-insensitive search in parent directory
    parent = os.path.dirname(expanded)
    basename = os.path.basename(expanded)

    if os.path.isdir(parent):
        try:
            result = subprocess.run(
                ["find", parent, "-maxdepth", "1", "-iname", basename],
                capture_output=True, text=True, timeout=5
            )
            matches = [m for m in result.stdout.strip().splitlines() if m]
            if matches:
                return matches[0], True
        except Exception:
            pass

    return expanded, False


def check_command_exists(binary):
    """Returns True if a binary is installed and runnable."""
    return which(binary)


def get_installed_alternatives(binary):
    """
    If a binary doesn't exist, suggest what is installed.
    E.g. 'calc' → suggests gnome-calculator.
    """
    suggestions = []
    for alias, candidates in APP_ALIASES.items():
        if binary in candidates:
            for c in candidates:
                if which(c) and c != binary:
                    suggestions.append(c)
    return suggestions