"""
__main__.py — process entry point: `python3 -m termio`.

Handles the one-time concerns that must run before the rest of the package
is imported: re-executing under the venv's interpreter if dependencies
aren't on the system Python, and enabling readline history.
"""

import sys
import os

try:
    import requests  # noqa: F401 — presence check only, to trigger the venv re-exec below
except ImportError:
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    venv_python = os.path.join(project_root, "venv", "bin", "python3")
    if os.path.exists(venv_python):
        os.execv(venv_python, [venv_python, "-m", "termio"] + sys.argv[1:])
    else:
        print("Could not find venv. Run the installer first.")
        sys.exit(1)

try:
    import readline
    readline.set_history_length(50)
except ImportError:
    pass

from .cli import main

main()
