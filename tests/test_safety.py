from termio.safety import check_command


def test_detects_rm_rf_root():
    dangerous, pattern = check_command("rm -rf /")
    assert dangerous is True
    assert pattern == "rm -rf /"


def test_detects_fork_bomb():
    dangerous, _ = check_command(":(){ :|:& };:")
    assert dangerous is True


def test_detects_dangerous_pattern_inside_longer_command():
    dangerous, pattern = check_command("sudo rm -rf / --no-preserve-root")
    assert dangerous is True
    assert pattern == "rm -rf /"


def test_safe_command_not_flagged():
    dangerous, pattern = check_command("ls -la ~/Documents")
    assert dangerous is False
    assert pattern is None


def test_case_insensitive_matching():
    dangerous, _ = check_command("SHUTDOWN now")
    assert dangerous is True


# ─── precise rm-target matching ─────────────────────────────────────────────────

def test_deleting_a_subdirectory_is_not_catastrophic():
    # Regression test: substring matching used to flag every absolute-path
    # delete as "rm -rf /" and every home-subdir delete as "rm -rf ~",
    # firing the scary "type yes to continue" prompt on normal deletes and
    # training users to blindly confirm it.
    for cmd in [
        "rm -rf ~/test",
        "rm -rf ~/Downloads/old",
        "rm -rf /home/zain/test",
        "rm -rf /tmp/build",
        "rm -rf ./node_modules",
    ]:
        dangerous, pattern = check_command(cmd)
        assert dangerous is False, f"{cmd!r} should not be catastrophic (got {pattern!r})"


def test_deleting_root_or_home_is_catastrophic():
    for cmd in ["rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/", "rm -fr $HOME", "rm -rf /home"]:
        dangerous, _ = check_command(cmd)
        assert dangerous is True, f"{cmd!r} should be catastrophic"


def test_non_recursive_rm_of_home_not_flagged():
    # `rm -f ~` without -r can't delete a directory, so it's not catastrophic.
    dangerous, _ = check_command("rm -f ~")
    assert dangerous is False


def test_recursive_chown_on_project_not_flagged():
    # Regression test: bare "chown -R" used to flag every recursive chown.
    dangerous, _ = check_command("chown -R zain:zain ~/projects/termio")
    assert dangerous is False
