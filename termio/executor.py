"""
executor.py — Runs generated commands in the persistent session shell.

Tracks the session's working directory across `cd` calls and detaches
GUI apps so they don't block the prompt.
"""

import os
import subprocess
import tempfile
import shlex

# GUI apps launched detached
DETACH_APPS = [
    "steam", "firefox", "chromium", "google-chrome", "brave-browser",
    "vlc", "mpv", "rhythmbox", "spotify", "code", "gedit",
    "nautilus", "thunar", "nemo", "xdg-open", "discord",
    "gnome-calculator", "kcalc", "mate-calc", "eog", "shotwell",
    "libreoffice", "gimp", "inkscape", "blender", "obs",
    "gnome-terminal", "konsole", "telegram-desktop", "slack", "zoom",
]

# Commands that install new software — refresh app cache after these run.
# Covers the major distro package managers so the cache stays correct
# whether the user is on Debian/Ubuntu, Fedora, Arch, openSUSE, or Alpine.
INSTALL_TRIGGERS = [
    "apt install", "apt-get install",
    "dnf install", "yum install",
    "pacman -s", "pacman --sync",
    "zypper install", "zypper in ",
    "apk add",
    "flatpak install", "snap install",
    "pip install", "pip3 install",
]


def is_install_command(commands):
    """Returns True if any command installs new software."""
    for cmd in commands:
        for trigger in INSTALL_TRIGGERS:
            if trigger in cmd.lower():
                return True
    return False


def should_detach(commands):
    for cmd in commands:
        first = cmd.strip().rstrip("&").split()[0].lower() if cmd.strip() else ""
        if first in DETACH_APPS or cmd.strip().startswith("xdg-open"):
            return True
    return False


def check_syntax(full_command):
    """
    Validate the shell syntax of a command before running it.
    Returns (is_valid, error_message).
    """
    try:
        result = subprocess.run(
            ["bash", "-n", "-c", full_command],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, None
    except Exception as e:
        # If we can't check syntax for some reason, don't block execution.
        return True, str(e)


# Cap how much output we keep around per run, so a noisy command
# (e.g. `find /`) can't blow up the conversation context fed to the AI.
MAX_CAPTURED_OUTPUT = 4000


def existing_dir(path):
    """
    Return `path` if it's a directory, else the nearest existing ancestor,
    falling back to the home directory. Guards against a session_cwd that was
    deleted out from under us — e.g. `rm -rf ~/test` while standing in ~/test,
    which would otherwise make the very next command crash with FileNotFound
    when Popen tries to start in a directory that no longer exists.
    """
    p = path
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p if p and os.path.isdir(p) else os.path.expanduser("~")


def run_commands_in_session(commands, session_cwd):
    """
    Run `commands` sequentially in `session_cwd`.
    Returns (success, new_session_cwd, output_text).
    """
    commands = [cmd.rstrip(" &") for cmd in commands]
    full_command = " && ".join(commands)

    # The directory may have been deleted by an earlier command — never hand
    # a nonexistent path to Popen's cwd= (it raises FileNotFoundError).
    session_cwd = existing_dir(session_cwd)

    if should_detach(commands):
        subprocess.Popen(
            full_command + " &",
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=session_cwd,
            executable="/bin/bash"
        )
        print("  Launched.\n")
        return True, session_cwd, ""

    # Capture the post-command cwd in a temp file as part of the SAME
    # execution, instead of re-running the commands a second time just
    # to read `pwd` (which would fire every side effect twice).
    cwd_fd, cwd_path = tempfile.mkstemp(prefix="termio_cwd_")
    os.close(cwd_fd)
    tracked_command = f"{full_command} && pwd > {shlex.quote(cwd_path)}"

    # stdin is closed (/dev/null) so a command that reads standard input —
    # e.g. a bare `wc -l`, `cat`, or `grep pattern` with no file, which the
    # model sometimes emits as its own pipeline stage — gets EOF immediately
    # instead of blocking the whole REPL forever waiting on the terminal.
    # sudo still prompts for a password normally: it reads /dev/tty, not stdin.
    proc = subprocess.Popen(
        tracked_command,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=session_cwd,
        executable="/bin/bash"
    )

    captured = []
    try:
        for line in proc.stdout:
            print(line, end="", flush=True)
            captured.append(line)
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  Interrupted.\n")
        os.unlink(cwd_path)
        return False, session_cwd, "".join(captured)[-MAX_CAPTURED_OUTPUT:]

    proc.wait()

    new_cwd = session_cwd
    try:
        with open(cwd_path, "r") as f:
            candidate = f.read().strip()
        if candidate and os.path.isdir(candidate):
            new_cwd = candidate
    except Exception:
        pass
    finally:
        os.unlink(cwd_path)

    # A command may have deleted the working directory itself (e.g.
    # `rm -rf ~/test` from inside ~/test) — fall back to a real directory so
    # the next prompt and command start somewhere valid.
    new_cwd = existing_dir(new_cwd)

    output_text = "".join(captured)[-MAX_CAPTURED_OUTPUT:]
    return proc.returncode == 0, new_cwd, output_text
