import os
import threading

from termio import executor


def test_stdin_reading_command_does_not_hang_the_repl(tmp_path):
    # Regression test: the model sometimes splits "find ... | wc -l" into two
    # array items ["find ...", "wc -l"], which Termio joins with &&. A bare
    # "wc -l" then reads standard input — and with stdin inherited from the
    # terminal it blocked the whole REPL forever until the user hit Ctrl+C.
    # stdin must be /dev/null so such commands get EOF and return immediately.
    result = {}

    def run():
        result["value"] = executor.run_commands_in_session(["echo hi", "wc -l"], str(tmp_path))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), "command hung reading stdin — stdin is not redirected to /dev/null"

    success, _, output = result["value"]
    assert success is True
    # wc -l counts zero lines from the empty stdin.
    assert output.strip().splitlines()[-1] == "0"


def test_command_runs_exactly_once(tmp_path):
    # Regression test: run_commands_in_session used to re-run the full
    # command chain a second time just to read `pwd`, duplicating every
    # side effect (file writes, installs, deletions, ...).
    marker = tmp_path / "marker.txt"
    success, _, _ = executor.run_commands_in_session(
        [f"echo run >> {marker}"], str(tmp_path)
    )
    assert success is True
    lines = marker.read_text().splitlines()
    assert lines == ["run"]


def test_cwd_updates_after_cd(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    success, new_cwd, _ = executor.run_commands_in_session(
        [f"cd {sub}"], str(tmp_path)
    )
    assert success is True
    assert new_cwd == str(sub)


def test_cwd_unchanged_on_failed_command(tmp_path):
    success, new_cwd, _ = executor.run_commands_in_session(
        ["false"], str(tmp_path)
    )
    assert success is False
    assert new_cwd == str(tmp_path)


def test_existing_dir_falls_back_to_nearest_ancestor(tmp_path):
    gone = tmp_path / "a" / "b" / "c"
    assert executor.existing_dir(str(gone)) == str(tmp_path)


def test_deleting_current_directory_does_not_crash_next_command(tmp_path):
    # Regression test: deleting the directory you're standing in (rm -rf ~/test
    # from inside ~/test) left session_cwd pointing at a deleted path, so the
    # NEXT command crashed with FileNotFoundError when Popen tried to start
    # there ("Unexpected error: No such file or directory: '/home/zain/test'").
    workdir = tmp_path / "test"
    workdir.mkdir()

    success, new_cwd, _ = executor.run_commands_in_session(
        [f"rm -rf {workdir}"], str(workdir)
    )
    # cwd must recover to an existing directory, not the deleted one.
    assert new_cwd != str(workdir)
    assert os.path.isdir(new_cwd)

    # The next command must run cleanly from the recovered directory.
    success, final_cwd, _ = executor.run_commands_in_session(["pwd"], new_cwd)
    assert success is True
    assert os.path.isdir(final_cwd)


def test_output_is_captured_for_conversation_context():
    _, _, output = executor.run_commands_in_session(["echo hello-world"], "/tmp")
    assert "hello-world" in output


def test_captured_output_is_capped_in_size():
    # A noisy command shouldn't be able to blow up the AI prompt context.
    _, _, output = executor.run_commands_in_session(
        ["yes x | head -n 100000"], "/tmp"
    )
    assert len(output) <= executor.MAX_CAPTURED_OUTPUT


def test_is_install_command_detects_apt_install():
    assert executor.is_install_command(["sudo apt install vim"]) is True
    assert executor.is_install_command(["ls -la"]) is False


def test_should_detach_for_gui_apps():
    assert executor.should_detach(["firefox"]) is True
    assert executor.should_detach(["ls -la"]) is False


def test_check_syntax_accepts_valid_command():
    valid, error = executor.check_syntax("echo hello && ls")
    assert valid is True
    assert error is None


def test_check_syntax_rejects_malformed_command():
    valid, error = executor.check_syntax("echo hello &&& ls")
    assert valid is False
    assert error
