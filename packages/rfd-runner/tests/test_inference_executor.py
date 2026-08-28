import subprocess

import pytest

from rfd_runner.inference_executor import STALL_EXIT_CODE, InferenceExecutor, _last_4kb


class FakePopen:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.returncode = None
        self._poll_value = None
        self.terminated = False
        self.killed = False
        self.wait_calls = []
        self._stderr = "stderr from fake process"

    def poll(self):
        return self._poll_value

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode

    def communicate(self):
        return (None, self._stderr)


def test_normal_per_step_completion(tmp_path):
    dump_dir = tmp_path
    proc = FakePopen(["cmd"])
    proc.returncode = 0

    def factory(argv, **kwargs):
        # Written as a side effect of Popen creation, which happens AFTER stale-dump clearing --
        # writing these before calling run_inference would make the clearing step sweep them up.
        (dump_dir / "0.pdb").write_text("ATOM ...\nTER")
        (dump_dir / "1.pdb").write_text("ATOM ...\nTER")
        return proc

    calls = []
    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=2,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: calls.append(a),
        popen_factory=factory,
        timeout_seconds=10,
        poll_interval_ms=1,
    )

    assert result.exit_code == 0
    assert [c[:2] for c in calls] == [(0, 0), (0, 1)]
    assert not (dump_dir / "0.pdb").exists()
    assert not (dump_dir / "1.pdb").exists()


def test_fast_final_write_still_ending_ter_is_success(tmp_path):
    dump_dir = tmp_path
    proc = FakePopen(["cmd"])
    proc._poll_value = 0  # already exited by the time we check
    proc.returncode = 0

    def factory(argv, **kwargs):
        (dump_dir / "0.pdb").write_text("ATOM ...\nTER")
        return proc

    calls = []
    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: calls.append(a),
        popen_factory=factory,
        timeout_seconds=10,
        poll_interval_ms=1,
    )

    assert result.exit_code == 0
    # This path breaks without calling on_step (business-logic-model.md section 3) -- exit_code
    # 0 alone is what distinguishes it from a real failure.
    assert calls == []


def test_nonzero_exit_no_valid_dump_returns_failure_with_last_4kb_stderr(tmp_path):
    dump_dir = tmp_path

    proc = FakePopen(["cmd"])
    proc._poll_value = 1
    proc.returncode = 1
    proc._stderr = "x" * 5000

    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: None,
        popen_factory=lambda *a, **k: proc,
        timeout_seconds=10,
        poll_interval_ms=1,
    )

    assert result.exit_code == 1
    assert len(result.stderr_tail) == 4096
    assert result.stderr_tail == "x" * 4096


def test_per_step_timeout_terminates_then_returns_stall_code(tmp_path):
    dump_dir = tmp_path
    proc = FakePopen(["cmd"])  # never exits, dump never appears

    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: None,
        popen_factory=lambda *a, **k: proc,
        timeout_seconds=-1,  # already-expired deadline -- deterministic, no real waiting
        poll_interval_ms=1,
    )

    assert proc.terminated is True
    assert proc.killed is False  # wait() succeeded without raising, so kill() was never needed
    assert result.exit_code == STALL_EXIT_CODE
    assert "step 0" in result.stderr_tail


def test_polls_multiple_times_before_dump_appears(tmp_path, monkeypatch):
    import rfd_runner.inference_executor as ie_module

    dump_dir = tmp_path
    proc = FakePopen(["cmd"])
    proc.returncode = 0
    dump_path = dump_dir / "0.pdb"

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        dump_path.write_text("ATOM ...\nTER")

    monkeypatch.setattr(ie_module.time, "sleep", fake_sleep)

    calls = []
    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: calls.append(a),
        popen_factory=lambda *a, **k: proc,
        timeout_seconds=10,
        poll_interval_ms=1,
    )

    assert len(sleep_calls) == 1  # had to wait exactly once before the dump appeared
    assert result.exit_code == 0
    assert len(calls) == 1


def test_stall_escalates_to_kill_when_terminate_does_not_stop_process(tmp_path):
    dump_dir = tmp_path
    proc = FakePopen(["cmd"])  # never exits, dump never appears

    wait_call_count = {"n": 0}

    def flaky_wait(timeout=None):
        wait_call_count["n"] += 1
        if wait_call_count["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)
        return proc.returncode

    proc.wait = flaky_wait

    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: None,
        popen_factory=lambda *a, **k: proc,
        timeout_seconds=-1,
        poll_interval_ms=1,
    )

    assert proc.terminated is True
    assert proc.killed is True
    assert result.exit_code == STALL_EXIT_CODE


def test_interrupt_escalates_to_kill_when_terminate_does_not_stop_process(tmp_path, monkeypatch):
    import rfd_runner.inference_executor as ie_module

    dump_dir = tmp_path
    proc = FakePopen(["cmd"])  # never exits, dump never appears -- polls forever

    wait_call_count = {"n": 0}

    def flaky_wait(timeout=None):
        wait_call_count["n"] += 1
        if wait_call_count["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)
        return proc.returncode

    proc.wait = flaky_wait

    class _Boom(Exception):
        pass

    def raising_check(path):
        raise _Boom("simulated interrupt while polling")

    monkeypatch.setattr(ie_module, "_dump_ends_with_ter", raising_check)

    with pytest.raises(_Boom):
        InferenceExecutor().run_inference(
            ["cmd"],
            total_steps=1,
            num_designs=1,
            dump_dir=dump_dir,
            on_step=lambda *a: None,
            popen_factory=lambda *a, **k: proc,
            timeout_seconds=10,
            poll_interval_ms=1,
        )

    assert proc.terminated is True
    assert proc.killed is True


def test_last_4kb_of_none_is_empty_string():
    assert _last_4kb(None) == ""
    assert _last_4kb("") == ""


def test_interrupt_during_polling_terminates_child_and_reraises(tmp_path, monkeypatch):
    import rfd_runner.inference_executor as ie_module

    dump_dir = tmp_path
    proc = FakePopen(["cmd"])  # never exits, dump never appears -- polls forever

    class _Boom(Exception):
        pass

    def raising_check(path):
        raise _Boom("simulated interrupt while polling")

    monkeypatch.setattr(ie_module, "_dump_ends_with_ter", raising_check)

    with pytest.raises(_Boom):
        InferenceExecutor().run_inference(
            ["cmd"],
            total_steps=1,
            num_designs=1,
            dump_dir=dump_dir,
            on_step=lambda *a: None,
            popen_factory=lambda *a, **k: proc,
            timeout_seconds=10,
            poll_interval_ms=1,
        )

    assert proc.terminated is True


def test_stale_dumps_cleared_before_popen_is_created(tmp_path):
    dump_dir = tmp_path
    stale = dump_dir / "0.pdb"
    stale.write_text("leftover from a previous attempt")

    observed = {}

    def factory(argv, **kwargs):
        observed["stale_present_at_popen"] = stale.is_file()
        proc = FakePopen(argv, **kwargs)
        proc._poll_value = 1
        proc.returncode = 1
        return proc

    calls = []
    result = InferenceExecutor().run_inference(
        ["cmd"],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: calls.append(a),
        popen_factory=factory,
        timeout_seconds=10,
        poll_interval_ms=1,
    )

    assert observed["stale_present_at_popen"] is False
    assert not stale.exists()
    assert result.exit_code == 1
    assert calls == []


def test_large_output_pipe_drain_avoids_deadlock(tmp_path):
    """Verifies that large stdout/stderr outputs (>64KB pipe buffer) are drained without deadlocking."""
    import sys
    dump_dir = tmp_path
    
    # Script that writes 150KB to stdout and 150KB to stderr while creating 0.pdb
    script = (
        "import sys, time, pathlib\n"
        "dump = pathlib.Path(sys.argv[1])\n"
        "for i in range(1000):\n"
        "    sys.stdout.write('A' * 200 + '\\n')\n"
        "    sys.stderr.write('B' * 200 + '\\n')\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.flush()\n"
        "(dump / '0.pdb').write_text('ATOM ...\\nTER')\n"
        "time.sleep(0.05)\n"
    )
    
    calls = []
    result = InferenceExecutor().run_inference(
        [sys.executable, "-c", script, str(dump_dir)],
        total_steps=1,
        num_designs=1,
        dump_dir=dump_dir,
        on_step=lambda *a: calls.append(a),
        timeout_seconds=5,
        poll_interval_ms=5,
    )
    
    assert result.exit_code == 0
    assert len(calls) == 1

