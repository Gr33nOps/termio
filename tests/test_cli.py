from termio import cli


# ─── strip_leading_article / looks_like_path ───────────────────────────────────

def test_strips_leading_article():
    assert cli.strip_leading_article("the /home/zain/projects/termio") == "/home/zain/projects/termio"
    assert cli.strip_leading_article("a video player") == "video player"
    assert cli.strip_leading_article("an apple") == "apple"
    assert cli.strip_leading_article("vlc") == "vlc"


def test_looks_like_path():
    assert cli.looks_like_path("/home/zain/projects/termio") is True
    assert cli.looks_like_path("~/Documents") is True
    assert cli.looks_like_path("./relative") is True
    assert cli.looks_like_path("vlc") is False
    assert cli.looks_like_path("video player") is False


def test_path_like_input_is_not_treated_as_app_name():
    # Regression test: "open the /home/zain/projects/termio" used to match
    # the globally-installed "termio" launcher via substring search and
    # relaunch the app instead of opening the folder.
    app_name = cli.strip_leading_article("the /home/zain/projects/termio")
    assert cli.looks_like_path(app_name) is True


def test_long_compound_open_request_skips_direct_resolution(monkeypatch):
    # Regression test: "open the termio folder that is in my projects
    # folder, please open it in file manager" is a compound natural-
    # language request, not a simple "open <app>" call. The direct-resolve
    # shortcut used to still run on it, matching shallow substrings (the
    # "file manager" alias, or the word "termio" itself) and launching the
    # wrong thing or relaunching Termio. Long requests should skip straight
    # to the AI layer, which has session context to find the real target.
    def boom(*args, **kwargs):
        raise AssertionError("resolve_app should not be called for long compound requests")

    monkeypatch.setattr(cli, "resolve_app", boom)
    result = cli.try_direct_open(
        "open the termio folder that is in projects folder. please open it in file manager"
    )
    assert result is False


def test_short_open_request_still_resolved_directly(monkeypatch):
    monkeypatch.setattr(cli, "resolve_app", lambda app_name: "firefox")
    monkeypatch.setattr("builtins.input", lambda _: "n")
    result = cli.try_direct_open("open firefox")
    assert result is True


def test_needs_ai_context_for_references_and_in_phrasing():
    # "open that folder in file manager" used to resolve to a bare "nemo"
    # launch (matching the "file manager" alias) with no folder, because the
    # direct shortcut has no memory of which folder "that" refers to.
    assert cli.needs_ai_context("that folder in file manager") is True
    assert cli.needs_ai_context("this in file manager") is True
    assert cli.needs_ai_context("it") is True
    assert cli.needs_ai_context("music in vlc") is True


def test_simple_app_name_does_not_need_ai_context():
    assert cli.needs_ai_context("firefox") is False
    assert cli.needs_ai_context("video player") is False


def test_demonstrative_open_defers_to_ai(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("resolve_app should not be called for 'that folder' references")

    monkeypatch.setattr(cli, "resolve_app", boom)
    assert cli.try_direct_open("open that folder in file manager") is False


# ─── conversation memory ───────────────────────────────────────────────────────

def setup_function(_):
    cli.conversation.clear()


def test_remember_turn_adds_entry():
    cli.remember_turn("list files", ["ls"], "a.txt\nb.txt")
    assert len(cli.conversation) == 1
    assert cli.conversation[0]["task"] == "list files"


def test_remember_turn_caps_history():
    for i in range(cli.MAX_CONTEXT_TURNS + 2):
        cli.remember_turn(f"task {i}", ["echo"], "")
    assert len(cli.conversation) == cli.MAX_CONTEXT_TURNS
    # Oldest turns should have been dropped, newest kept.
    assert cli.conversation[-1]["task"] == f"task {cli.MAX_CONTEXT_TURNS + 1}"


def test_build_context_includes_previous_output():
    cli.remember_turn(
        "find termio folders",
        ["find ~ -type d -name termio"],
        "/home/zain/termio\n/home/zain/projects/termio",
    )
    context = cli.build_context()
    assert "find termio folders" in context
    assert "/home/zain/projects/termio" in context


def test_build_context_truncates_long_output():
    long_output = "x" * (cli.MAX_OUTPUT_CHARS_IN_CONTEXT + 500)
    cli.remember_turn("noisy task", ["find /"], long_output)
    context = cli.build_context()
    # The truncated tail should be present; the full untruncated blob should not.
    assert long_output not in context
    assert long_output[-50:] in context


# ─── find_missing_binaries ──────────────────────────────────────────────────────

def test_shell_keywords_are_not_flagged_as_missing_binaries():
    # Regression test: a command like an inline if/then/fi block has "if"
    # as its first word, but "if" is a shell keyword, not a binary on PATH.
    cmd = 'if [ -d ~/termio ]; then echo found; fi'
    assert cli.find_missing_binaries([cmd]) == []


def test_real_missing_binary_still_flagged():
    cmd = "this-binary-does-not-exist-xyz --version"
    missing = cli.find_missing_binaries([cmd])
    assert len(missing) == 1
    assert missing[0][1] == "this-binary-does-not-exist-xyz"


def test_shell_builtins_are_not_flagged_as_missing_binaries():
    # Regression test: "source venv/bin/activate" was flagged as needing
    # an installable "source" binary, but source/export/alias/etc. are
    # pure shell builtins with no standalone executable on PATH at all.
    for cmd in ["source myenv/bin/activate", "export PATH=$PATH:~/bin", "unset FOO"]:
        assert cli.find_missing_binaries([cmd]) == []


# ─── dry run prefix parsing ─────────────────────────────────────────────────────

def test_dry_run_prefix_matches_with_task():
    m = cli.DRY_RUN_PREFIX.match("dry run delete old logs")
    assert m is not None
    assert "dry run delete old logs"[m.end():].strip() == "delete old logs"


def test_bare_dry_run_does_not_match_prefix_but_matches_bare_check():
    # Regression test: bare "dry run" with no task used to fall through
    # DRY_RUN_PREFIX unmatched and get sent to the AI as a literal task
    # string instead of showing a usage hint.
    assert cli.DRY_RUN_PREFIX.match("dry run") is None
    assert cli.DRY_RUN_BARE.match("dry run") is not None
    assert cli.DRY_RUN_BARE.match("DRYRUN") is not None
    assert cli.DRY_RUN_BARE.match("dry run open firefox") is None
