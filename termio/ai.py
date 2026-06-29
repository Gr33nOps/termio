import requests
import re
import json
import shutil
import functools

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_BASE = "http://localhost:11434"

# Major Linux package managers, in detection order. Termio should generate
# install commands for whichever one this machine actually has, so it works
# on Debian/Ubuntu/Mint, Fedora/RHEL, Arch, openSUSE and Alpine — not only apt.
PACKAGE_MANAGERS = [
    ("apt",    "sudo apt install -y",        "sudo apt update"),
    ("dnf",    "sudo dnf install -y",        "sudo dnf check-update"),
    ("pacman", "sudo pacman -S --noconfirm", "sudo pacman -Sy"),
    ("zypper", "sudo zypper install -y",     "sudo zypper refresh"),
    ("apk",    "sudo apk add",               "sudo apk update"),
    ("yum",    "sudo yum install -y",        "sudo yum check-update"),
]


@functools.lru_cache(maxsize=1)
def detect_package_manager():
    """Return (name, install_cmd, update_cmd) for this system, or None."""
    for name, install, update in PACKAGE_MANAGERS:
        if shutil.which(name):
            return (name, install, update)
    return None


def _package_manager_hint():
    pm = detect_package_manager()
    if not pm:
        return ""
    name, install, update = pm
    return (
        f"\n- THIS SYSTEM'S PACKAGE MANAGER IS '{name}'. To install software, "
        f"use '{install} <package>' (run '{update}' first if a refresh is "
        f"needed). Never use a different distro's package manager."
    )

# Cold-start generous timeout: on a CPU-only laptop the *first* request also
# has to load the model into RAM, which can take far longer than a warm one.
REQUEST_TIMEOUT = 180


def is_ollama_running():
    """Quick check whether the Ollama server is reachable at all."""
    try:
        requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except requests.exceptions.RequestException:
        return False


def available_models():
    """List the model names currently pulled in Ollama (empty list on error)."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return []


def model_is_available(model, models=None):
    """
    True if `model` is pulled. Matches both the exact tag and the base name,
    so "qwen2.5-coder:3b" matches a pulled "qwen2.5-coder:3b" and a bare
    "qwen2.5-coder" matches any pulled tag of it.
    """
    if models is None:
        models = available_models()
    if not models:
        # Can't tell (server unreachable / old version) — don't false-alarm.
        return True
    base = model.split(":")[0]
    return any(m == model or m.split(":")[0] == base for m in models)


def warm_up(model):
    """
    Preload the model into memory with a tiny request. Run this in a background
    thread at startup so the user's first real command isn't stuck waiting for
    the model to load (the cause of the "Could not reach Ollama" on first try).
    """
    try:
        requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": "ok", "stream": False,
                  "options": {"num_predict": 1}},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException:
        pass

# ─── Package replacement map ──────────────────────────────────────────────────
# Matched with \b...\b word boundaries (see apply_package_replacements), so
# "python" alone correctly covers python-pip, python-dev, etc. too — the
# hyphen is a non-word character and still satisfies the trailing \b.
PACKAGE_REPLACEMENTS = {
    "youtube-dl":         "yt-dlp",
    "python":             "python3",
    "easy_install":       "pip3",
    "mplayer":            "mpv",
    "git-core":           "git",
    "nodejs-legacy":      "nodejs",
    "ifconfig":           "ip addr",
    "netstat":            "ss",
    "nslookup":           "dig",
    "apt-get install":    "apt install",
    "apt-get update":     "apt update",
    "apt-get upgrade":    "apt upgrade",
    "apt-get remove":     "apt remove",
    "apt-get autoremove": "apt autoremove",
    "apt-get purge":      "apt purge",
    # Note: 'open ' replacement handled carefully in apply_package_replacements
}

# ─── Intent detection ─────────────────────────────────────────────────────────
EXPLAIN_KEYWORDS = [
    "what is", "what's", "what are", "what does", "what should",
    "explain", "tell me about", "describe",
    "which is better", "which one is",
    "how does", "how do i know", "why is", "why does", "why should",
    "is there a", "is it possible", "can you tell",
    "difference between", "compare",
    "what tool", "what package", "what program",
    "best way to", "best tool", "best package", "best app",
    "good tool", "good package", "good app",
    "help me understand", "what happens when",
]

QUESTION_STARTERS = (
    "what ", "why ", "how does", "which ", "who ", "where ",
    "when ", "is ", "are ", "can ", "could ", "should ",
    "do i need", "does ",
)

# Phrases that look like questions but are really actionable requests about
# the local filesystem — "what's inside my downloads", "what are the files in
# this folder", "how many logs in /var". These must run as commands (ls/find/
# wc), not be deflected with the "Termio runs commands, not explanations" hint.
COMMAND_OVERRIDES = (
    "inside",
    "how many",
    "number of",
    "contents of",
    " in my ",
    " in this ",
    " in the ",
    " in that ",
    " in /",
    " in ~",
    # Possessive info queries — "what is my ip / hostname / username / kernel"
    # are things to print, not concepts to explain.
    "what is my ",
    "what's my ",
    "whats my ",
    "what are my ",
    "what was my ",
)

# Imperative action verbs. If the request contains one, it's a thing to DO,
# not a question to answer — even when politely phrased ("can you open this
# file", "could you make a folder"). Without this, the leading "can "/"could "
# question-starters wrongly deflected real commands with the unhelpful
# "Termio runs commands, not explanations" hint.
ACTION_VERBS = (
    "open", "launch", "start", "run", "make", "create", "delete", "remove",
    "find", "search", "show", "list", "install", "download", "copy", "move",
    "rename", "write", "save", "compress", "extract", "zip", "unzip", "kill",
    "mount", "unmount", "update", "upgrade", "count", "change", "edit", "play",
    "convert", "resize", "print", "go to", "navigate", "mkdir", "touch", "add",
)

def is_explain_intent(user_input):
    text = user_input.lower().strip()
    # Filesystem-content queries win even if phrased as a "what is..." question.
    if any(signal in text for signal in COMMAND_OVERRIDES):
        return False
    # An imperative action verb means "do this", not "explain this".
    if any(re.search(r"\b" + re.escape(verb) + r"\b", text) for verb in ACTION_VERBS):
        return False
    for keyword in EXPLAIN_KEYWORDS:
        if keyword in text:
            return True
    if text.startswith(QUESTION_STARTERS):
        return True
    return False


# ─── URL detection ────────────────────────────────────────────────────────────
URL_NEEDED_PATTERNS = [
    r"\bdownload\b.{0,30}\byoutube\b",
    r"\byoutube\b.{0,30}\bdownload\b",
    r"\bdownload\b.{0,40}\bsong\b",
    r"\bdownload\b.{0,40}\bmusic\b",
    r"\bdownload\b.{0,40}\bvideo\b.{0,20}\byoutube\b",
    r"\byt-dlp\b.{0,40}\b(song|music|video)\b",
]

URL_PRESENT_PATTERN = r"https?://"

# "download a music player" / "download a video editor" is an INSTALL request,
# not a media download — these words mean the user wants software, so don't
# demand a URL. Without this, "download best music player" matched the
# download+music pattern and was wrongly deflected with "this needs a URL".
INSTALL_INDICATORS = (
    "player", "editor", "browser", "app", "application", "software",
    "package", "program", "tool", "client", "ide", "terminal",
    "for linux", "open source", "open-source",
)

def needs_url(user_input):
    text = user_input.lower().strip()
    if re.search(URL_PRESENT_PATTERN, user_input):
        return False
    if any(indicator in text for indicator in INSTALL_INDICATORS):
        return False
    for pattern in URL_NEEDED_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


# ─── System prompts (JSON output) ─────────────────────────────────────────────
COMMAND_PROMPTS = {
    "linux": """You are a Linux bash command generator. You are a shell compiler, not a chatbot.

OUTPUT FORMAT — you MUST return a valid JSON object and nothing else:
{"commands": ["cmd1", "cmd2"], "confidence": 90}

RULES:
- commands: array of raw bash commands only, one per item
- confidence: integer 0-100 (how confident the commands are correct)
- No explanations inside commands array — commands only
- No markdown, no backticks, no code fences outside the JSON
- No numbered lists, no bullet points
- Never put text or explanations in the commands array
- A PIPELINE is ONE command: keep it in a single array item, e.g.
  {"commands": ["find / -type d -name 'foo' 2>/dev/null | wc -l"]}.
  NEVER split a pipeline across array items and NEVER emit a bare filter
  like "wc -l", "grep x", "sort", "head", or "awk ..." as its own command —
  on its own it has no input and will hang. Pipe it onto the command that
  feeds it instead.
- Never use placeholders like <filename>, VIDEO_ID, /path/to/
- Use absolute or home-relative paths where possible
- INSTALLING SOFTWARE: "install X", "download X", "get X", "download the best
  X" where X is an app/program/player/editor/browser/tool ALWAYS means install
  it with THIS SYSTEM'S package manager (named in the System context below),
  or with flatpak if it's a flatpak app. NEVER open a download web page for
  software, NEVER scrape a download link with wget/grep/sed, and NEVER download
  a release tarball. Just install the package.
  Examples (using this system's installer): "download best music player"
  -> install the 'vlc' package ; "a lightweight image viewer" -> install 'feh'
- NEVER invent, guess, or fabricate URLs. Only use a URL the user typed
  verbatim. Do not produce xdg-open with a made-up https:// link.
- xdg-open is ONLY for opening the user's OWN local files/folders, or a URL
  the user explicitly provided — never for installing software.
- For YouTube downloads use yt-dlp with ytsearch: prefix for name-based searches
- Use apt not apt-get
- Use python3 not python
- Use yt-dlp not youtube-dl
- Use mpv or vlc not mplayer
- Use ip addr not ifconfig
- SCOPE: "my pc", "my whole pc", "my computer", "entire system", "everywhere"
  mean search the whole filesystem from / — use: find / -name '...' 2>/dev/null
  (add sudo only if needed). They do NOT mean the current directory.
- SCOPE: "my X folder/directory" means the home subdirectory ~/X
  (e.g. "my projects folder" = ~/projects, "my downloads" = ~/Downloads).
  Never default to the current directory for these.
- To COUNT things, pipe to wc -l, e.g.
  find / -type d -name 'foo' 2>/dev/null | wc -l — do NOT print a raw
  listing when the user asked "how many" or "number of".
- Do NOT chain a listing into grep -c on a separate line; keep a count in
  one pipeline.
- If "System context" includes output from a previous command (e.g. a list
  of paths), use it ONLY when the new task refers back to it ("the second
  one", "that file", "it", "the one I just found") — pick the matching item
  from that output. If the new task is self-contained and unrelated to the
  previous one, IGNORE the previous context entirely.
- Avoid generating multiple commands that search the same or an equivalent
  scope (e.g. /home/<user> and ~ are the same directory) — pick one
- If confidence below 70, still return best guess but set confidence accordingly""",
}

# ─── Invalid command line patterns ───────────────────────────────────────────
INVALID_LINE_PATTERNS = [
    r"<[^>]+>",
    r"\bVIDEO_ID\b",
    r"\bSONG_ID\b",
    r"/path/to/",
    r"\[your",
    r"\[file",
    r"\[name",
    r"example\.com",
    r"placeholder",
    r"^if\s+you",
    r"^note[:\s]",
    r"^replace\s",
    r"^alternatively",
    r"^on\s+(centos|fedora|rhel|debian|ubuntu)",
    r"^\s*-\s+on\s+",
    r"^\s*\*\s",
    r"^please\s",
    r"^you\s+can\s",
    r"^this\s+will\s",
    r"^make\s+sure\s",
    r"^ensure\s",
    r"^for\s+example",
    r"^warning[:\s]",
    r"^tip[:\s]",
    r"^explanation[:\s]",
    r"^note[:\s]",
]

def is_valid_command(line):
    line_lower = line.lower().strip()
    for pattern in INVALID_LINE_PATTERNS:
        if re.search(pattern, line_lower):
            return False
    return True

def apply_package_replacements(command):
    for old, new in PACKAGE_REPLACEMENTS.items():
        pattern = r'\b' + re.escape(old) + r'\b'
        command = re.sub(pattern, new, command)

    # Fix 'open X' → 'xdg-open X'
    # Use regex to only match 'open' at start of command, never touch xdg-open
    command = re.sub(r'^open\s+', 'xdg-open ', command)

    # Fix accidental double xdg-open (xdg-xdg-open)
    command = re.sub(r'\bxdg-xdg-open\b', 'xdg-open', command)

    return command

def clean_commands(commands):
    """Clean a list of raw command strings."""
    cleaned = []
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue
        if cmd.startswith("#"):
            continue
        if not is_valid_command(cmd):
            continue
        cmd = apply_package_replacements(cmd)
        cleaned.append(cmd)
    return cleaned

def _extract_json_object(raw):
    """
    Find and parse the first JSON object with a "commands" key in `raw`.

    Uses json.JSONDecoder.raw_decode at each candidate '{' instead of a
    brace-balanced regex, because commands routinely contain literal braces
    themselves (e.g. awk '{print $2}', find -exec ... {} +) which a regex
    like r'\\{[^{}]*\\}' can never match across.
    """
    decoder = json.JSONDecoder()
    start = raw.find("{")
    while start != -1:
        try:
            data, _ = decoder.raw_decode(raw, start)
            if isinstance(data, dict) and "commands" in data:
                return data
        except json.JSONDecodeError:
            pass
        start = raw.find("{", start + 1)
    return None


def _extract_commands_array_loosely(raw):
    """
    Best-effort recovery when the model emits almost-valid JSON but breaks
    it with an unescaped quote inside a command string — a common small-model
    mistake, e.g. encoding `grep -i "error"` inside an already double-quoted
    JSON string without escaping. A strict JSON parser can never accept this,
    so we locate the "commands": [...] span by regex and pull out each
    quoted item using a lazy match anchored on ", or "$ (a closing quote
    immediately followed by the next item or end of array), which correctly
    skips over interior unescaped quotes that aren't in that position.
    """
    match = re.search(r'"commands"\s*:\s*\[(.*?)\]\s*,?\s*"confidence"', raw, re.DOTALL)
    if not match:
        match = re.search(r'"commands"\s*:\s*\[(.*)\]', raw, re.DOTALL)
    if not match:
        return None
    items = re.findall(r'"(.*?)"(?=\s*,|\s*$)', match.group(1), re.DOTALL)
    items = [item.replace('\\"', '"').strip() for item in items]
    return [item for item in items if item]


def parse_ai_response(raw):
    """
    Parse JSON response from AI.
    Returns (commands list, confidence int).
    Falls back to raw line parsing if JSON fails.
    """
    raw = raw.strip()

    # Try to extract JSON object from response
    try:
        data = _extract_json_object(raw)
        if data:
            commands = data.get("commands", [])
            confidence = int(data.get("confidence", 80))
            if isinstance(commands, list) and commands:
                return clean_commands(commands), confidence
    except (ValueError, KeyError):
        pass

    # The JSON was malformed, but it may still contain a recognizable
    # "commands": [...] array we can recover with a looser pass.
    loose_commands = _extract_commands_array_loosely(raw)
    if loose_commands:
        confidence_match = re.search(r'"confidence"\s*:\s*(\d+)', raw)
        confidence = int(confidence_match.group(1)) if confidence_match else 70
        return clean_commands(loose_commands), confidence

    # Fallback: parse as raw line-by-line commands
    lines = raw.splitlines()
    fallback = []
    for line in lines:
        line = line.strip()
        # Skip JSON-looking lines
        if line.startswith(("{", "}", "[", "]", '"commands"', '"confidence"')):
            continue
        # Strip numbering
        if re.match(r"^\d+[\.\)]\s+", line):
            line = re.sub(r"^\d+[\.\)]\s+", "", line).strip()
        # Strip backticks
        line = re.sub(r"```[a-z]*", "", line).replace("`", "").strip()
        if line and is_valid_command(line):
            fallback.append(apply_package_replacements(line))

    return fallback, 60  # Low confidence since JSON parse failed


def get_command(user_input, model, extra_context=""):
    """
    Returns (commands list, confidence int) or (None, 0) on connection/timeout error.
    """
    system_prompt = COMMAND_PROMPTS["linux"] + _package_manager_hint()

    pm = detect_package_manager()
    pm_context = f"Package manager: {pm[0]} (install with '{pm[1]} <pkg>'). " if pm else ""

    prompt = f"{system_prompt}\n\nTask: {user_input}"
    if pm_context or extra_context:
        prompt += f"\n\nSystem context: {pm_context}{extra_context}"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw = response.json()["response"].strip()
        return parse_ai_response(raw)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return None, 0
    except Exception:
        return [], 0