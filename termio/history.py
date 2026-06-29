"""
history.py — Command audit log

Records every task Termio was asked to run, the commands it generated,
and whether they were actually executed, so users can review what
happened in a session after the fact.
"""

import json
import os
import time

# Data files live at the project root (one level up from this package),
# not inside the installed package itself.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(PROJECT_ROOT, "termio_history.jsonl")
MAX_ENTRIES = 500


def log_entry(task, commands, confidence, executed, returncode=None):
    """Append one audit record. Never raises — logging must not break the app."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": task,
        "commands": commands,
        "confidence": confidence,
        "executed": executed,
        "returncode": returncode,
    }
    try:
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        _trim_if_needed()
    except Exception:
        pass


def _trim_if_needed():
    """Keep the log from growing unbounded."""
    with open(HISTORY_FILE, "r") as f:
        lines = f.readlines()
    if len(lines) > MAX_ENTRIES * 2:
        with open(HISTORY_FILE, "w") as f:
            f.writelines(lines[-MAX_ENTRIES:])


def read_history(limit=20):
    """Return the most recent `limit` history entries, oldest first."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            lines = f.readlines()
    except Exception:
        return []

    entries = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def print_history(limit=20):
    entries = read_history(limit)
    if not entries:
        print("  No command history yet.\n")
        return
    print()
    for e in entries:
        status = "ran" if e.get("executed") else "cancelled"
        rc = e.get("returncode")
        rc_label = f" exit={rc}" if rc is not None else ""
        print(f"  [{e.get('timestamp', '?')}] ({status}{rc_label}) {e.get('task', '')}")
        for cmd in e.get("commands", []):
            print(f"      {cmd}")
    print()
