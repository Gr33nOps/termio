"""
ui.py — Terminal display and input-sanitization helpers.
"""

import re


def divider():
    print("  " + "─" * 46)


def print_task_box(task, commands, confidence, shell_label="Bash"):
    print()
    divider()
    print(f"  Task    {task}")
    print(f"  Shell   {shell_label}   Confidence  {confidence}%")
    divider()
    if len(commands) == 1:
        print(f"  {commands[0]}")
    else:
        for i, cmd in enumerate(commands, 1):
            print(f"  {i}.  {cmd}")
    divider()
    print()


def sanitize_input(text):
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()


def is_garbage_input(text):
    if not text:
        return True
    letters = sum(1 for c in text if c.isalpha())
    total = len(text)
    if total > 5 and letters / total < 0.3:
        return True
    if re.search(r'(.)\1{7,}', text):
        return True
    return False
