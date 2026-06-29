"""
safety.py — Detects catastrophic commands before they run.

The matcher deliberately distinguishes "delete this subdirectory" (normal,
allowed after the usual y/n) from "delete the whole filesystem or home dir"
(catastrophic, requires typing 'yes'). A naive substring check flags
`rm -rf /home/zain/test` as `rm -rf /`, which trains users to blindly
confirm the scary prompt and defeats the entire feature.
"""

import re

# Unambiguously destructive — flagged anywhere they appear (case-insensitive).
SUBSTRING_PATTERNS = [
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    ":(){ :|:& };:",
    "chmod -r 777 /",
    "> /dev/sd",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
]

# Recursive deletion of one of these wipes the whole system or home dir.
# Matched only when the target is EXACTLY one of these — not a subpath like
# ~/test or /home/zain/project, which are normal deletes.
_CATASTROPHIC_TARGETS = {
    "/", "/*",
    "~", "~/",
    "$home", "$home/", "${home}", "${home}/",
    "/home", "/home/", "/home/*",
    "/root", "/root/",
}


def _catastrophic_rm_target(command):
    """
    Returns the catastrophic target string if `command` contains an `rm`
    that recursively deletes the filesystem root or home directory, else None.
    """
    for segment in re.split(r"[|;&\n]+", command):
        tokens = [t.strip("'\"") for t in segment.split()]
        if "rm" not in tokens:
            continue
        rest = tokens[tokens.index("rm") + 1:]
        flags = [t for t in rest if t.startswith("-")]
        targets = [t for t in rest if not t.startswith("-")]

        recursive = any(
            f == "--recursive" or (not f.startswith("--") and "r" in f.lower())
            for f in flags
        )
        if not recursive:
            continue

        for target in targets:
            if target.lower() in _CATASTROPHIC_TARGETS:
                return target
    return None


def check_command(command):
    """Returns (is_dangerous, matched_pattern)."""
    command_lower = command.lower().strip()

    for pattern in SUBSTRING_PATTERNS:
        if pattern in command_lower:
            return True, pattern

    target = _catastrophic_rm_target(command)
    if target:
        return True, f"rm -rf {target}"

    return False, None
