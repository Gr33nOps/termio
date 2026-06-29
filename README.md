# Termio

**Local AI English-to-Terminal Command Translator**

Termio converts plain English into terminal commands using a local AI model via Ollama. Fully offline, no API keys, no cloud — everything runs on your machine.

Supports **Linux** only.

---

## How It Works

1. You describe what you want to do in plain English
2. Termio sends it to a local AI model running via Ollama
3. The AI returns one or more bash commands
4. A safety check runs on every command
5. You confirm before anything executes

---

## Example

```
==================================================
         Termio — AI Terminal Assistant
  Model: qwen2.5-coder:3b  |  Shell: Bash
  Type 'exit' to quit  |  'setup' to reconfigure
==================================================

🟢 What do you want to do?
> create a folder called projects and go inside it

⏳ Thinking...

Generated Commands (Bash) — 2 steps:
  1. mkdir projects
  2. cd projects

Run all 2 commands in sequence? (y/n): y

── Step 1/2: mkdir projects
── Step 2/2: cd projects
```

---

## Requirements

- Python 3.8 or higher
- [Ollama](https://ollama.com)
- Linux

---

## Installation

```bash
git clone https://github.com/Gr33nOps/termio.git
cd termio
bash install.sh
```

That's it. The installer will:
- Check Python and Ollama are installed
- Create the virtual environment automatically
- Install all dependencies
- Create a global `termio` launcher so you can run it from anywhere

> After install, open a **new** terminal and type `termio` from anywhere.

---

## First Run

On first launch Termio will ask you to choose your model:
```
  1  qwen2.5-coder:3b   ⭐ Recommended   ~2GB    Fast    Low-end hardware, daily use
  2  qwen2.5-coder:7b   🔥 Best Quality  ~4.5GB  Medium  Better hardware, complex commands
  3  llama3.2:3b        ✅ Good          ~2GB    Fast    General use, lightweight
  ...
```

Your choices are saved. To reconfigure later, type `setup` inside Termio.

---

## Pull Your Model

After setup, pull your chosen model (only needed once):

```bash
ollama pull qwen2.5-coder:3b
```

---

## Usage

After install just type from anywhere:

```bash
termio
```

No activation, no cd, no path needed. Works from any folder.

---

## Model Guide

| # | Model | Rating | Size | Speed | Best For |
|---|---|---|---|---|---|
| 1 | qwen2.5-coder:3b | ⭐ Recommended | ~2GB | Fast | Low-end hardware, daily use |
| 2 | qwen2.5-coder:7b | 🔥 Best Quality | ~4.5GB | Medium | Better hardware, complex commands |
| 3 | llama3.2:3b | ✅ Good | ~2GB | Fast | General use, lightweight |
| 4 | mistral:7b | ✅ Good | ~4.5GB | Medium | General purpose tasks |
| 5 | deepseek-coder:6.7b | 💡 Decent | ~4GB | Medium | Code-heavy tasks |
| 6 | codellama:7b | ⚠️ Okay | ~4.5GB | Slow | Not recommended for Termio |

**Choosing by hardware (be realistic):**
- **No dedicated GPU, ≤ 8GB RAM** → stay on `qwen2.5-coder:3b` (option 1). It's
  the default for a reason: it's purpose-built for code, gives the best results
  *per gigabyte*, and leaves room for the rest of your system. A 7B model
  (~4.5GB) will swap or get OOM-killed on an 8GB laptop.
- **16GB+ RAM, or any dedicated GPU** → `qwen2.5-coder:7b` (option 2) is
  noticeably more accurate on complex, multi-step requests.
- You can also enter any custom Ollama model name during setup.

**What to expect:** Termio translates plain English into shell commands with a
small local model, so it is fast and private but **not infallible** — it can
still occasionally produce a wrong or oddly-scoped command. That's why every
command is shown to you and requires confirmation before running. Always read
the command before pressing `y`. A 7B model reduces these misses if your
hardware can handle it.

---

## Platform Support

Works on any Linux distribution with a Bash shell. Termio **auto-detects your
package manager**, so "install vlc" becomes the right command for your system:

| Distro family | Package manager | Install command Termio generates |
|---|---|---|
| Debian / Ubuntu / Mint | `apt` | `sudo apt install -y vlc` |
| Fedora / RHEL | `dnf` | `sudo dnf install -y vlc` |
| Arch / Manjaro | `pacman` | `sudo pacman -S --noconfirm vlc` |
| openSUSE | `zypper` | `sudo zypper install -y vlc` |
| Alpine | `apk` | `sudo apk add vlc` |

---

## Multi-Step Commands

Termio handles tasks that need more than one command automatically.

```
🟢 What do you want to do?
> update the system and clean up old packages

⏳ Thinking...

Generated Commands (Bash) — 3 steps:
  1. sudo apt update
  2. sudo apt upgrade -y
  3. sudo apt autoremove -y

Run all 3 commands in sequence? (y/n): y

── Step 1/3: sudo apt update
── Step 2/3: sudo apt upgrade -y
── Step 3/3: sudo apt autoremove -y
```

---

## Safety System

Two-tier confirmation with dangerous pattern detection.

**Safe commands:**
```
Run it? (y/n):
```

**Dangerous commands:**
```
⚠️  WARNING — Dangerous pattern detected in: 'rm -rf /'
   Matched pattern: 'rm -rf /'

One or more commands above could cause serious damage to your system.
Type 'yes' to run all anyway, anything else to cancel:
```

Nothing ever runs without your explicit confirmation.

---

## Built-in Commands

| Type | Action |
|---|---|
| `exit` / `quit` / `q` | Close Termio |
| `setup` | Reconfigure model |
| `refresh apps` | Rescan installed applications |
| `history` | Show past commands and whether they ran |
| `forget` | Clear session memory (see below) |
| `dry run <task>` | Preview the generated commands without executing them |
| `Ctrl+C` | Force quit |

---

## Session Memory

Termio remembers the last few tasks and what they actually output, and feeds that back to the AI so follow-up requests can reference them:

```
[~]> find termio folders in my pc
...
/home/zain/termio
/home/zain/projects/termio

[~]> open the second one in file explorer
...
  xdg-open /home/zain/projects/termio
```

Memory is in-process only (cleared on exit), capped to the last 3 tasks, and each task's captured output is truncated before being sent to the AI so a noisy command (e.g. `find /`) can't blow up the prompt. Type `forget` to clear it manually mid-session.

---

## Dry Run Mode

Prefix any task with `dry run` to see exactly what Termio would do, without it actually running:

```
[~]> dry run delete all .tmp files in this folder

  ──────────────────────────────────────────────
  Task    delete all .tmp files in this folder
  Shell   Bash   Confidence  92%
  ──────────────────────────────────────────────
  find . -name "*.tmp" -delete
  ──────────────────────────────────────────────

  (dry run — not executed)
```

---

## Command History

Every task Termio generates a command for is logged to `termio_history.jsonl`, whether or not you ran it. Type `history` to review the last 20 entries (timestamp, task, commands, and whether it ran):

```
[~]> history

  [2026-06-29 12:11:34] (ran exit=0) create a file called notes.txt
      touch ~/notes.txt
```

---

## Project Structure

```
termio/                       # repo root
├── termio/                   # the actual package
│   ├── __main__.py           # process entry point (python3 -m termio)
│   ├── cli.py                # interactive loop and command handlers
│   ├── ai.py                 # Ollama API handler and prompt logic
│   ├── executor.py           # runs commands in the persistent session shell
│   ├── ui.py                 # display/input helpers (boxes, sanitization)
│   ├── safety.py             # danger pattern detection
│   ├── config.py             # first-run setup, model selection
│   ├── history.py            # command audit log (termio_history.jsonl)
│   └── resolver.py           # app/path resolution against the local system
├── tests/                    # pytest suite, one file per package module
├── install.sh                # installer for Linux
├── requirements.txt          # runtime dependencies
├── requirements-dev.txt      # + pytest, for running the test suite
├── conftest.py
├── .gitignore
├── LICENSE
└── README.md
```

Data files Termio creates at runtime (`termio_config.json`, `termio_history.jsonl`, `app_cache.json`) live at the repo root, alongside `install.sh` — not inside the `termio/` package — so they survive package upgrades and are easy to find.

---

## Running Tests

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest tests/ -v
```

---

## Troubleshooting

**`❌ Could not reach Ollama`**
```bash
ollama serve
```

**`❌ The AI returned an empty response`**
Try rephrasing with more detail.

**`❌ The AI returned an explanation instead of a command`**
Keep input short and specific:
- ✅ `compress this folder`
- ❌ `can you please compress this folder into a zip if possible`

---

## Limitations

- Works best with clear, specific descriptions
- No memory of previous commands in a session
- Safety filter is rule-based, not AI-driven
- Terminal only, no GUI

---

## Future Plans

- Session memory for context-aware commands
- Plugin support for git, docker, etc.
- AI-assisted safety validation
- Inline command explanations

---

## Tech Stack

| Component | Tool |
|---|---|
| Language | Python 3 |
| LLM Runtime | Ollama |
| Default Model | qwen2.5-coder:3b |
| HTTP Client | requests |
| Shell Execution | subprocess |
| Platforms | Linux |

---

## License

MIT License — free to use, modify, and distribute.