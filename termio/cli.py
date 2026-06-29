"""
cli.py — Termio's interactive loop and command handlers.

The process bootstrap (venv re-exec, readline setup) lives in __main__.py;
this module assumes its dependencies are already importable.
"""

import os
import re
import threading

from .ai import (
    get_command, is_explain_intent, needs_url,
    is_ollama_running, warm_up, available_models, model_is_available,
)
from .safety import check_command
from .config import load_config, reset_config
from .resolver import resolve_app, verify_path, check_command_exists, get_installed_alternatives, refresh_cache
from .ui import divider, print_task_box, sanitize_input, is_garbage_input
from .executor import run_commands_in_session, is_install_command, check_syntax
from . import history

# Binaries we trust without an explicit existence check (core coreutils etc.)
TRUSTED_BINARIES = (
    "echo", "cat", "ls", "cd", "mkdir", "touch", "rm", "mv", "cp", "find",
    "grep", "sudo", "apt", "pip", "git", "python3", "node", "zip", "tar",
    "wget", "curl", "xdg-open", "yt-dlp",
)

# Shell keywords and builtins aren't binaries — e.g. an "if [ ... ]; then
# ...; fi" command has "if" as its first word, and "source venv/bin/activate"
# has "source", but neither has a standalone executable on PATH to check for.
SHELL_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "function", "select", "time", "in",
    "source", "export", "alias", "unalias", "unset", "eval", "exec",
    "wait", "declare", "local", "let", "readonly", "shopt", "getopts", "trap",
}

# Intents that open an app — we try to resolve before calling AI
OPEN_PATTERNS = [
    r"^open\s+(.+)",
    r"^launch\s+(.+)",
    r"^start\s+(.+)",
    r"^run\s+(.+?)(\s+from|\s+in|$)",
]

# Destructive commands that need extra caution on low confidence
DESTRUCTIVE_PATTERNS = [
    r"\brm\b", r"\bdelete\b", r"\bremove\b",
    r"\bmkdir\b", r"\btouch\b", r"\bmv\b",
    r"\bformat\b", r"\bdrop\b",
]

DRY_RUN_PREFIX = re.compile(r"^dry\s*run[:\s]+", re.IGNORECASE)
DRY_RUN_BARE = re.compile(r"^dry\s*run$", re.IGNORECASE)
LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def strip_leading_article(text):
    return LEADING_ARTICLE.sub("", text, count=1).strip()


def looks_like_path(text):
    return text.startswith(("~", "/", "./", "../"))


# Above this many words, "open X" is no longer a simple app/file launch —
# it's a compound natural-language request ("open the termio folder that is
# in my projects folder, please open it in file manager"). Those need the
# AI layer, which has session context to find the actual target; the direct
# shortcut below only does shallow substring/alias matching and either
# launches the wrong thing or, worse, matches Termio's own name.
MAX_DIRECT_OPEN_WORDS = 6

# Reference words ("open *that* folder", "open *it*") point at something from
# an earlier turn, and "open X *in* file manager" means "open X using Y" —
# both need conversation context the direct shortcut doesn't have, so they
# must defer to the AI layer instead of being matched as a literal app name.
DEMONSTRATIVES = {"that", "this", "it", "them", "those", "these"}


def needs_ai_context(app_name):
    """True if an open-target references prior context or names a target app."""
    words = set(app_name.lower().split())
    if words & DEMONSTRATIVES:
        return True
    if " in " in f" {app_name.lower()} ":
        return True
    return False

# ─── Session state ────────────────────────────────────────────────────────────
session_cwd = os.path.expanduser("~")

# Rolling conversation memory: lets follow-up requests like "open the second
# one" or "delete that file" resolve against what the last command actually
# produced. In-memory only — cleared on exit, or manually via "forget".
MAX_CONTEXT_TURNS = 3
MAX_OUTPUT_CHARS_IN_CONTEXT = 600
conversation = []


def remember_turn(task, commands, output):
    conversation.append({"task": task, "commands": commands, "output": output or ""})
    while len(conversation) > MAX_CONTEXT_TURNS:
        conversation.pop(0)


def build_context():
    parts = [f"Current directory: {session_cwd}. Shell: bash."]
    for turn in conversation:
        cmds = "; ".join(turn["commands"])
        out = turn["output"].strip()
        if len(out) > MAX_OUTPUT_CHARS_IN_CONTEXT:
            out = out[-MAX_OUTPUT_CHARS_IN_CONTEXT:]
        entry = f"Previous task: {turn['task']}\nPrevious commands run: {cmds}"
        if out:
            entry += f"\nPrevious output:\n{out}"
        parts.append(entry)
    return "\n\n".join(parts)


def is_destructive(commands):
    for cmd in commands:
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, cmd.lower()):
                return True
    return False


def first_binary_of(command):
    """Returns the first binary a command line would invoke, skipping a leading 'sudo'."""
    words = command.split()
    if words and words[0] == "sudo":
        words = words[1:]
    return words[0] if words else ""


def find_missing_binaries(commands):
    """Returns a list of (command, binary) pairs for binaries that aren't installed."""
    missing = []
    for cmd in commands:
        binary = first_binary_of(cmd)
        if not binary or binary in SHELL_KEYWORDS:
            continue
        if not binary.startswith(TRUSTED_BINARIES):
            if not check_command_exists(binary):
                missing.append((cmd, binary))
    return missing


# Extracts the topic of a "what is X" / "tell me about X" style question.
EXPLAIN_SUBJECT = re.compile(
    r"(?:what(?:'s| is| are)|tell me about|about|describe|explain)\s+"
    r"(?:a |an |the )?(.+?)[\s?.!]*$",
    re.IGNORECASE,
)


# ─── Handlers ─────────────────────────────────────────────────────────────────
def handle_explain(user_input):
    print()
    print("  Termio runs commands — it doesn't answer questions.")
    print()
    text = user_input.lower()
    if any(w in text for w in ["video player", "media player", "music player"]):
        print("  Try:  install vlc")
    elif "screenshot" in text:
        print("  Try:  install flameshot")
    elif any(w in text for w in ["compress", "zip"]):
        print("  Try:  compress this folder into a zip")
    else:
        # Use the actual subject of the question for a relevant suggestion
        # instead of a canned, unrelated example.
        match = EXPLAIN_SUBJECT.search(user_input.strip())
        subject = match.group(1).strip() if match else ""
        # Keep it to a short noun phrase; drop trailing comparison clauses.
        subject = re.split(r"\b(?:or|vs|versus|better|instead)\b", subject)[0].strip()
        if subject and len(subject.split()) <= 4:
            print(f"  If it's a program, try:   install {subject}")
            print(f"  To launch it, try:        open {subject}")
        else:
            print("  Rephrase it as an action, e.g.:")
            print("    install <program>   |   open <app>   |   create a file called notes.txt")
    print()


def try_direct_open(user_input):
    """
    Layer 2: Try to resolve 'open X' requests directly from the
    system resolver without calling the AI at all.
    Returns True if handled, False if AI should handle it.
    """
    global session_cwd
    text = user_input.strip()

    for pattern in OPEN_PATTERNS:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            app_name = strip_leading_article(match.group(1).strip())
            is_path_like = looks_like_path(app_name)

            # Compound/long requests, references to a previous turn ("that
            # folder"), and "open X in Y" phrasing aren't simple app launches
            # — defer to the AI layer instead of risking a shallow, wrong match.
            if not is_path_like and (
                len(app_name.split()) > MAX_DIRECT_OPEN_WORDS
                or needs_ai_context(app_name)
            ):
                return False

            # If it's clearly a filesystem path, don't risk an app-name
            # substring match (e.g. a path ending in ".../termio" matching
            # the installed "termio" launcher itself) — go straight to path.
            binary = None if is_path_like else resolve_app(app_name)
            if binary:
                print()
                divider()
                print(f"  Task    {user_input}")
                print(f"  App     {binary}  (resolved from '{app_name}')")
                divider()
                print(f"  {binary}")
                divider()
                print()
                try:
                    confirm = input("  Launch it? (y/n): ").strip().lower()
                except KeyboardInterrupt:
                    print("\n  Cancelled.\n")
                    return True
                if confirm == "y":
                    print()
                    _, session_cwd, output = run_commands_in_session([binary], session_cwd)
                    remember_turn(user_input, [binary], output)
                    print()
                else:
                    print("  Cancelled.\n")
                return True

            # Try to resolve as a path
            possible_path = app_name if is_path_like else f"~/{app_name}"
            actual_path, found = verify_path(possible_path)
            if found:
                cmd = f"xdg-open {actual_path}"
                print()
                divider()
                print(f"  Task    {user_input}")
                print(f"  Path    {actual_path}")
                divider()
                print(f"  {cmd}")
                divider()
                print()
                try:
                    confirm = input("  Open it? (y/n): ").strip().lower()
                except KeyboardInterrupt:
                    print("\n  Cancelled.\n")
                    return True
                if confirm == "y":
                    _, session_cwd, output = run_commands_in_session([cmd], session_cwd)
                    remember_turn(user_input, [cmd], output)
                    print()
                else:
                    print("  Cancelled.\n")
                return True

    return False


def handle_command(user_input, model, dry_run=False):
    global session_cwd

    # Check if task needs a real URL
    if needs_url(user_input):
        print()
        print("  This task needs a real URL.")
        print("  The AI cannot look things up on the internet.")
        print()
        print("  Instead of: 'download billie jean from youtube'")
        print("  Try:        'download https://youtube.com/watch?v=ID as mp3'")
        print()
        print("  Copy the URL from your browser and paste it here.")
        print()
        return

    # Layer 2: Try to resolve directly without AI (skipped in dry-run mode,
    # since it executes immediately on confirmation rather than previewing)
    if not dry_run and try_direct_open(user_input):
        return

    # Layer 3: Ask AI
    print("\n  Understanding request...\n")

    context = build_context()

    try:
        commands, confidence = get_command(user_input, model, extra_context=context)
    except KeyboardInterrupt:
        print("\n  Cancelled.\n")
        return

    if commands is None:
        print("  Could not reach Ollama. Start it with:  ollama serve\n")
        return

    if not commands:
        print("  Could not generate a valid command.")
        print("  Try rephrasing or being more specific.\n")
        return

    # Validate shell syntax first — a genuine syntax error (e.g. a missing
    # semicolon before `fi`) should be reported as exactly that, not
    # misdiagnosed as a missing binary by the check below.
    full_command = " && ".join(cmd.rstrip(" &") for cmd in commands)
    valid_syntax, syntax_error = check_syntax(full_command)
    if not valid_syntax:
        print()
        print("  The generated commands have invalid shell syntax and were not run.")
        print(f"  {syntax_error}")
        print()
        history.log_entry(user_input, commands, confidence, executed=False)
        return

    # Verify every command's binary exists, not just the first
    missing = find_missing_binaries(commands)
    if missing:
        print()
        for cmd, binary in missing:
            print(f"  '{binary}' is not installed on this system (needed for: {cmd})")
            alternatives = get_installed_alternatives(binary)
            if alternatives:
                print(f"    Installed alternatives: {', '.join(alternatives)}")
                print(f"    Try: open {alternatives[0]}")
            else:
                print(f"    Try: install {binary}")
        print()
        history.log_entry(user_input, commands, confidence, executed=False)
        return

    # Show command box
    print_task_box(user_input, commands, confidence, "Bash")

    if dry_run:
        print("  (dry run — not executed)\n")
        history.log_entry(user_input, commands, confidence, executed=False)
        return

    # Warn on low confidence
    if confidence < 70:
        print(f"  ⚠  Low confidence ({confidence}%). Review carefully before running.")
        if is_destructive(commands):
            print("  ⚠  This includes destructive operations. Be extra careful.")
        print()

    # Warn on destructive + low confidence
    if confidence < 50 and is_destructive(commands):
        print("  Confidence too low for a destructive command. Cancelled for safety.\n")
        history.log_entry(user_input, commands, confidence, executed=False)
        return

    # Safety check
    any_dangerous = False
    for cmd in commands:
        dangerous, pattern = check_command(cmd)
        if dangerous:
            any_dangerous = True
            print(f"  ⚠  Dangerous pattern: '{pattern}'")

    # Confirmation
    try:
        if any_dangerous:
            print("  This could cause serious damage.")
            confirm = input("  Type 'yes' to run anyway: ").strip()
            if confirm.lower() != "yes":
                print("  Cancelled.\n")
                history.log_entry(user_input, commands, confidence, executed=False)
                return
        else:
            if len(commands) == 1:
                confirm = input("  Run it? (y/n): ").strip().lower()
            else:
                confirm = input(f"  Run all {len(commands)} commands? (y/n): ").strip().lower()
            if confirm != "y":
                print("  Cancelled.\n")
                history.log_entry(user_input, commands, confidence, executed=False)
                return
    except KeyboardInterrupt:
        print("\n  Cancelled.\n")
        history.log_entry(user_input, commands, confidence, executed=False)
        return

    print()
    success, session_cwd, output = run_commands_in_session(commands, session_cwd)
    print()
    history.log_entry(user_input, commands, confidence, executed=True,
                       returncode=0 if success else 1)
    remember_turn(user_input, commands, output)

    # Auto-refresh app cache if something was installed
    if is_install_command(commands):
        refresh_cache()
        print("  App cache updated — new apps are now available.\n")

    if session_cwd != os.path.expanduser("~"):
        print(f"  Now in: {session_cwd}\n")


# ─── Main loop ────────────────────────────────────────────────────────────────
def main():
    global session_cwd

    config = load_config()
    model = config.get("model", "qwen2.5-coder:3b")

    # Preload the model in the background so the first command isn't stuck
    # waiting for it to load into RAM (the "Could not reach Ollama" first-try
    # failure). The user reads the banner / types while this runs.
    if is_ollama_running():
        if not model_is_available(model, available_models()):
            print()
            print(f"  ⚠  The model '{model}' isn't pulled yet.")
            print(f"     Pull it once with:  ollama pull {model}")
            print("     (or type 'setup' to pick a model you already have)")
            print()
        else:
            threading.Thread(target=warm_up, args=(model,), daemon=True).start()
    else:
        print()
        print("  ⚠  Ollama doesn't seem to be running.")
        print("     Start it in another terminal with:  ollama serve")
        print()

    print()
    print("  ══════════════════════════════════════════════")
    print("         Termio  —  AI Terminal Assistant")
    print(f"    Model  {model}")
    print(f"    Shell  Bash")
    print("    Type  exit  to quit  |  setup  to reconfigure")
    print("    Type  history  to view past commands")
    print("    Type  forget   to clear session memory")
    print("    Prefix 'dry run' to preview without executing")
    print("  ══════════════════════════════════════════════")
    print()

    while True:
        cwd_display = session_cwd.replace(os.path.expanduser("~"), "~")
        try:
            user_input = input(f"[{cwd_display}]> ")
        except KeyboardInterrupt:
            print("\n\n  Goodbye!\n")
            break
        except EOFError:
            print("\n  Goodbye!\n")
            break

        user_input = sanitize_input(user_input)

        if user_input.lower() in ["exit", "quit", "q"]:
            print("\n  Goodbye!\n")
            break

        if user_input.lower() == "setup":
            config = reset_config()
            model = config.get("model", "qwen2.5-coder:3b")
            print(f"  Now using: {model} on Bash\n")
            continue

        if user_input.lower() == "refresh apps":
            refresh_cache()
            print("  App cache refreshed.\n")
            continue

        if user_input.lower() in ("history", "history show"):
            history.print_history()
            continue

        if user_input.lower() in ("forget", "forget context", "reset context"):
            conversation.clear()
            print("  Session memory cleared.\n")
            continue

        if not user_input:
            continue

        if is_garbage_input(user_input):
            print("  Please describe your task in plain English.\n")
            continue

        if DRY_RUN_BARE.match(user_input):
            print("  Usage: dry run <task>   (e.g. 'dry run delete old logs')\n")
            continue

        dry_run = False
        dry_match = DRY_RUN_PREFIX.match(user_input)
        if dry_match:
            dry_run = True
            user_input = user_input[dry_match.end():].strip()

        if len(user_input) < 4:
            print("  Input too short.\n")
            continue

        try:
            if is_explain_intent(user_input):
                handle_explain(user_input)
            else:
                handle_command(user_input, model, dry_run=dry_run)
        except KeyboardInterrupt:
            print("\n  Cancelled.\n")
        except Exception as e:
            print(f"  Unexpected error: {e}\n")
