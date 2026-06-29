import os
import re

from termio import resolver


# ─── alias word-boundary matching ──────────────────────────────────────────────

def test_alias_matches_as_whole_word():
    assert any(
        re.search(r'\b' + re.escape(alias) + r'\b', "open code")
        for alias in resolver.APP_ALIASES
    )


def test_alias_does_not_match_inside_unrelated_word():
    # Regression test: substring matching used to fire "code" inside "decode"
    # and "codecov", and "music" inside "musical".
    text = "decode this codecov musical report"
    matches = [
        alias for alias in resolver.APP_ALIASES
        if re.search(r'\b' + re.escape(alias) + r'\b', text)
    ]
    assert "code" not in matches
    assert "music" not in matches


# ─── which / check_command_exists ──────────────────────────────────────────────

def test_which_finds_real_binary():
    assert resolver.which("ls") is True


def test_which_rejects_fake_binary():
    assert resolver.which("this-binary-does-not-exist-xyz") is False


def test_check_command_exists_matches_which():
    assert resolver.check_command_exists("ls") is True
    assert resolver.check_command_exists("this-binary-does-not-exist-xyz") is False


# ─── verify_path ────────────────────────────────────────────────────────────────

def test_verify_path_finds_existing_file(tmp_path):
    f = tmp_path / "real_file.txt"
    f.write_text("hi")
    actual, found = resolver.verify_path(str(f))
    assert found is True
    assert actual == str(f)


def test_verify_path_fuzzy_matches_case_insensitively(tmp_path):
    f = tmp_path / "Resume.PDF"
    f.write_text("hi")
    actual, found = resolver.verify_path(str(tmp_path / "resume.pdf"))
    assert found is True
    assert actual == str(f)


def test_verify_path_missing_file_not_found(tmp_path):
    actual, found = resolver.verify_path(str(tmp_path / "nope.txt"))
    assert found is False


def test_verify_path_does_not_double_expand_home():
    # Regression test: callers used to prepend "~/" even when the path was
    # already absolute or already "~"-prefixed, producing "~/~/..." paths.
    home_file = os.path.expanduser("~/.bashrc")
    if os.path.exists(home_file):
        actual, found = resolver.verify_path("~/.bashrc")
        assert found is True
        assert actual == home_file


# ─── self-resolution guard ──────────────────────────────────────────────────────

def test_termio_launcher_excluded_from_app_cache():
    # Regression test: the globally-installed "termio" launcher script in
    # /usr/local/bin was being scanned into the app cache like any other
    # binary, so ANY request that merely mentioned the word "termio" (e.g.
    # "open the termio folder in my projects") could match it via the
    # cache's substring lookup and relaunch the app inside itself.
    cache = resolver.scan_desktop_files()
    assert "termio" not in cache
