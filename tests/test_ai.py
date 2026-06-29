import json

from termio import ai


# ─── apply_package_replacements ───────────────────────────────────────────────

def test_replaces_known_packages():
    assert ai.apply_package_replacements("youtube-dl video") == "yt-dlp video"
    assert ai.apply_package_replacements("python script.py") == "python3 script.py"
    assert ai.apply_package_replacements("mplayer video.mp4") == "mpv video.mp4"
    assert ai.apply_package_replacements("ifconfig") == "ip addr"


def test_does_not_corrupt_substrings_containing_a_package_name():
    # Regression test: a naive str.replace() used to turn these into
    # "ipython3" and "gmpv", corrupting unrelated commands/binaries.
    assert ai.apply_package_replacements("ipython script.py") == "ipython script.py"
    assert ai.apply_package_replacements("gmplayer video.mp4") == "gmplayer video.mp4"


def test_apt_get_normalized_to_apt():
    assert ai.apply_package_replacements("sudo apt-get install vim") == "sudo apt install vim"
    assert ai.apply_package_replacements("sudo apt-get update") == "sudo apt update"


def test_python_dash_suffixes_still_normalized():
    # "python" with \b boundaries still covers python-pip, python-dev, etc.
    assert ai.apply_package_replacements("apt install python-pip") == "apt install python3-pip"


def test_open_rewritten_to_xdg_open():
    assert ai.apply_package_replacements("open file.txt") == "xdg-open file.txt"


def test_double_xdg_open_collapsed():
    assert ai.apply_package_replacements("xdg-open file.txt") == "xdg-open file.txt"


# ─── is_valid_command ──────────────────────────────────────────────────────────

def test_rejects_placeholder_lines():
    assert ai.is_valid_command("yt-dlp <VIDEO_ID>") is False
    assert ai.is_valid_command("cp /path/to/file ~") is False
    assert ai.is_valid_command("note: this requires sudo") is False


def test_accepts_real_commands():
    assert ai.is_valid_command("mkdir ~/projects") is True
    assert ai.is_valid_command("sudo apt install vim") is True


# ─── needs_url ─────────────────────────────────────────────────────────────────

def test_needs_url_for_vague_youtube_request():
    assert ai.needs_url("download billie jean from youtube") is True


def test_no_url_needed_when_url_present():
    assert ai.needs_url("download https://youtube.com/watch?v=abc as mp3") is False


def test_no_url_needed_for_unrelated_task():
    assert ai.needs_url("create a folder called test") is False


# ─── is_explain_intent ─────────────────────────────────────────────────────────

def test_explain_intent_detected():
    assert ai.is_explain_intent("what is yt-dlp") is True
    assert ai.is_explain_intent("explain how docker works") is True


def test_command_intent_not_flagged_as_explain():
    assert ai.is_explain_intent("install vlc") is False
    assert ai.is_explain_intent("create a folder called test") is False


def test_filesystem_queries_are_not_explain():
    # Regression test: "what is inside my projects folder" was deflected with
    # the "Termio runs commands, not explanations" hint because it contains
    # the substring "what is" — but it's a real request to list contents.
    for t in [
        "what is inside my projects folder?",
        "what's inside my downloads",
        "what are the files in this folder",
        "how many termio folders are in my pc",
        "what is in my home directory",
    ]:
        assert ai.is_explain_intent(t) is False, f"{t!r} should be treated as a command"


def test_genuine_definition_questions_still_explain():
    for t in ["what is yt-dlp", "what is docker", "which is better vim or nano"]:
        assert ai.is_explain_intent(t) is True, f"{t!r} should be treated as explain"


def test_possessive_info_queries_are_commands():
    # Regression test: "what is my ip address" was deflected as a question,
    # but it's a request to print system info (ip addr / hostname).
    for t in ["what is my ip address", "what is my hostname",
              "what's my username", "what is my kernel version"]:
        assert ai.is_explain_intent(t) is False, f"{t!r} should be a command"


# ─── package manager portability ────────────────────────────────────────────────

def test_detect_package_manager_returns_known_tool(monkeypatch):
    ai.detect_package_manager.cache_clear()
    monkeypatch.setattr(ai.shutil, "which", lambda name: name == "pacman")
    pm = ai.detect_package_manager()
    ai.detect_package_manager.cache_clear()
    assert pm is not None
    assert pm[0] == "pacman"
    assert "pacman" in pm[1]


def test_package_manager_hint_names_the_detected_manager(monkeypatch):
    ai.detect_package_manager.cache_clear()
    monkeypatch.setattr(ai.shutil, "which", lambda name: name == "dnf")
    hint = ai._package_manager_hint()
    ai.detect_package_manager.cache_clear()
    assert "dnf" in hint


def test_package_manager_hint_empty_when_none_found(monkeypatch):
    ai.detect_package_manager.cache_clear()
    monkeypatch.setattr(ai.shutil, "which", lambda name: False)
    assert ai._package_manager_hint() == ""
    ai.detect_package_manager.cache_clear()


# ─── model availability ─────────────────────────────────────────────────────────

def test_model_is_available_exact_and_base_match():
    pulled = ["qwen2.5-coder:3b", "llama3.2:3b"]
    assert ai.model_is_available("qwen2.5-coder:3b", pulled) is True
    assert ai.model_is_available("qwen2.5-coder", pulled) is True
    assert ai.model_is_available("mistral:7b", pulled) is False


def test_model_is_available_no_false_alarm_when_list_unknown():
    # If we can't list models (server unreachable), don't warn the user.
    assert ai.model_is_available("anything", []) is True


def test_politely_phrased_commands_are_not_explain():
    # Regression test: "can you open this txt file" / "could you make a folder"
    # were deflected as questions because they start with "can "/"could ".
    # An imperative action verb means it's a command, however it's phrased.
    for t in [
        "can you open this txt file now?",
        "can you make a text file and write hello in it",
        "could you delete that folder",
        "can you show me the files here",
    ]:
        assert ai.is_explain_intent(t) is False, f"{t!r} should be treated as a command"


def test_install_request_does_not_need_url():
    # Regression test: "download best music player" matched the download+music
    # pattern and was wrongly told it needs a URL — it's an install request.
    for t in [
        "download best open source music player",
        "download best music player for linux that is open source",
        "download a video editor",
    ]:
        assert ai.needs_url(t) is False, f"{t!r} is an install, should not need a URL"


def test_real_media_download_still_needs_url():
    for t in ["download billie jean song from youtube", "download this music from youtube"]:
        assert ai.needs_url(t) is True, f"{t!r} should still need a URL"


# ─── ollama reachability / warm-up ──────────────────────────────────────────────

def test_is_ollama_running_true_when_reachable(monkeypatch):
    monkeypatch.setattr(ai.requests, "get", lambda *a, **k: None)
    assert ai.is_ollama_running() is True


def test_is_ollama_running_false_when_unreachable(monkeypatch):
    def boom(*a, **k):
        raise ai.requests.exceptions.ConnectionError()
    monkeypatch.setattr(ai.requests, "get", boom)
    assert ai.is_ollama_running() is False


def test_warm_up_never_raises(monkeypatch):
    def boom(*a, **k):
        raise ai.requests.exceptions.ConnectionError()
    monkeypatch.setattr(ai.requests, "post", boom)
    # warm_up must swallow errors — it runs in a background thread at startup.
    ai.warm_up("qwen2.5-coder:3b")


def test_get_command_uses_generous_timeout(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"response": '{"commands": ["ls"], "confidence": 90}'}

    def fake_post(url, json=None, timeout=None):
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(ai.requests, "post", fake_post)
    ai.get_command("list files", "qwen2.5-coder:3b")
    # A cold start must not be cut off by a short timeout.
    assert captured["timeout"] >= 120


# ─── parse_ai_response ─────────────────────────────────────────────────────────

def test_parses_well_formed_json():
    raw = json.dumps({"commands": ["mkdir test", "cd test"], "confidence": 95})
    commands, confidence = ai.parse_ai_response(raw)
    assert commands == ["mkdir test", "cd test"]
    assert confidence == 95


def test_falls_back_to_line_parsing_on_bad_json():
    raw = "mkdir test\ncd test"
    commands, confidence = ai.parse_ai_response(raw)
    assert commands == ["mkdir test", "cd test"]
    assert confidence == 60


def test_strips_invalid_lines_from_fallback():
    raw = "1. mkdir test\nNote: this creates a folder\n2. cd test"
    commands, _ = ai.parse_ai_response(raw)
    assert commands == ["mkdir test", "cd test"]


def test_parses_json_with_markdown_fence():
    raw = '```json\n{"commands": ["ls -la"], "confidence": 90}\n```'
    commands, confidence = ai.parse_ai_response(raw)
    assert commands == ["ls -la"]
    assert confidence == 90


def test_parses_commands_containing_literal_braces():
    # Regression test: the old brace-balanced regex required zero braces
    # between the outer { and }, so any command containing literal braces
    # (awk '{print $2}', find -exec ... {} +, etc.) broke JSON extraction
    # entirely and the line-by-line fallback discarded it too, leaving an
    # empty command list ("Could not generate a valid command").
    raw = (
        '```json\n{\n  "commands": ["find / -name \'termio\'", '
        '"grep \'termio\' $(du -h --max-depth=1 | sort -nr | head -n 2 '
        '| awk \'{print $2}\')"],\n  "confidence": 90\n}\n```'
    )
    commands, confidence = ai.parse_ai_response(raw)
    assert len(commands) == 2
    assert "awk '{print $2}'" in commands[1]
    assert confidence == 90


def test_parses_find_exec_with_braces():
    raw = json.dumps({"commands": ["find . -name '*.tmp' -exec rm {} +"], "confidence": 88})
    commands, _ = ai.parse_ai_response(raw)
    assert commands == ["find . -name '*.tmp' -exec rm {} +"]


def test_recovers_commands_from_malformed_json_with_unescaped_quotes():
    # Regression test: small models sometimes embed a quoted sub-string
    # (e.g. grep -i "error") inside an already double-quoted JSON command
    # string without escaping it. That's genuinely invalid JSON — no parser
    # can accept it — but the intended commands are still recoverable.
    raw = (
        '```json\n{\n  "commands": ["find /home/zain -name \'log*\' -type f '
        '-exec grep -i "error" {} +", "ls -la /home/zain | tail -n 1"],\n'
        '  "confidence": 85\n}\n```'
    )
    commands, confidence = ai.parse_ai_response(raw)
    assert commands == [
        'find /home/zain -name \'log*\' -type f -exec grep -i "error" {} +',
        "ls -la /home/zain | tail -n 1",
    ]
    assert confidence == 85
