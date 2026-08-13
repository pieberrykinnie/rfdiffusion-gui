from pathlib import Path

import pytest

from rfd_runner.__main__ import _parse_args
from rfd_runner.orchestrator import Stage


def test_parse_args_defaults_to_stage_all():
    args = _parse_args(["/some/run/dir"])
    assert args.run_dir == Path("/some/run/dir")
    assert args.stage == Stage.ALL.value


def test_parse_args_accepts_explicit_stage():
    args = _parse_args(["/some/run/dir", "--stage", "validate"])
    assert args.stage == Stage.VALIDATE.value


def test_parse_args_rejects_unknown_stage():
    with pytest.raises(SystemExit):
        _parse_args(["/some/run/dir", "--stage", "bogus"])


def test_module_invokes_orchestrator_main_and_exits_with_its_return_code(monkeypatch):
    import runpy
    import sys

    calls = []

    def fake_main(run_dir, stage=Stage.ALL):
        calls.append((run_dir, stage))
        return 3

    monkeypatch.setattr("rfd_runner.orchestrator.main", fake_main)
    monkeypatch.setattr(sys, "argv", ["rfd_runner", "/some/run/dir", "--stage", "backbone"])
    sys.modules.pop("rfd_runner.__main__", None)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("rfd_runner.__main__", run_name="__main__")

    assert exc_info.value.code == 3
    assert calls == [(Path("/some/run/dir"), Stage.BACKBONE)]
