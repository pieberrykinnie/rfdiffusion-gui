from pathlib import Path

from rfd_core import DesignRequest

from rfd_runner.validation_executor import ValidationExecutor


class FakePopen:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.returncode = 0

    def communicate(self):
        return (None, "some stderr")


def _make_request(**overrides):
    defaults = dict(
        name="design",
        contigs="A1-10",
        partition="gpu",
        walltime="0-01:00:00",
    )
    defaults.update(overrides)
    return DesignRequest(**defaults)


def test_val_argv_matches_field_for_field(tmp_path):
    request = _make_request(
        num_seqs=16,
        num_recycles=3,
        rm_aa="CM",
        mpnn_sampling_temp=0.2,
        num_designs=4,
    )
    captured = {}

    def factory(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakePopen(argv, **kwargs)

    ValidationExecutor().run_validation(
        tmp_path,
        "design",
        ["A1-10/20-20", "A1-10/20-20"],
        copies=2,
        request=request,
        popen_factory=factory,
        cwd=Path("/opt/weights/alphafold"),
    )

    argv = captured["argv"]
    assert argv[0] == "/app/RFdiffusion/.venv/bin/python"
    assert argv[1:3] == ["-m", "colabdesign.rf.designability_test"]
    assert f"--pdb={tmp_path}/design_0.pdb" in argv
    assert f"--loc={tmp_path}/design" in argv
    assert "--contig=A1-10/20-20:A1-10/20-20" in argv
    assert "--copies=2" in argv
    assert "--num_seqs=16" in argv
    assert "--num_recycles=3" in argv
    assert "--rm_aa=CM" in argv
    assert "--mpnn_sampling_temp=0.2" in argv
    assert "--num_designs=4" in argv
    # None of the optional flags were requested.
    assert "--initial_guess" not in argv
    assert "--use_multimer" not in argv
    assert "--use_soluble" not in argv


def test_optional_flags_appended_only_when_set(tmp_path):
    request = _make_request(initial_guess=True, use_multimer=True, use_soluble_mpnn=True)
    captured = {}

    def factory(argv, **kwargs):
        captured["argv"] = argv
        return FakePopen(argv, **kwargs)

    ValidationExecutor().run_validation(
        tmp_path, "design", ["A1-10/20-20"], copies=1, request=request, popen_factory=factory
    )

    argv = captured["argv"]
    assert "--initial_guess" in argv
    assert "--use_multimer" in argv
    assert "--use_soluble" in argv


def test_cwd_defaults_to_runner_config_af_params_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RFD_AF_PARAMS", "/custom/af-params")
    request = _make_request()
    captured = {}

    def factory(argv, **kwargs):
        captured["kwargs"] = kwargs
        return FakePopen(argv, **kwargs)

    ValidationExecutor().run_validation(
        tmp_path, "design", ["A1-10/20-20"], copies=1, request=request, popen_factory=factory
    )

    assert captured["kwargs"]["cwd"] == "/custom/af-params"


def test_cwd_is_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("RFD_AF_PARAMS", "/should-not-be-used")
    request = _make_request()
    captured = {}

    def factory(argv, **kwargs):
        captured["kwargs"] = kwargs
        return FakePopen(argv, **kwargs)

    ValidationExecutor().run_validation(
        tmp_path,
        "design",
        ["A1-10/20-20"],
        copies=1,
        request=request,
        popen_factory=factory,
        cwd=Path("/explicit/override"),
    )

    assert captured["kwargs"]["cwd"] == "/explicit/override"


def test_returns_inference_result_with_exit_code_and_stderr_tail(tmp_path):
    request = _make_request()

    def factory(argv, **kwargs):
        proc = FakePopen(argv, **kwargs)
        proc.returncode = 7
        return proc

    result = ValidationExecutor().run_validation(
        tmp_path, "design", ["A1-10/20-20"], copies=1, request=request, popen_factory=factory
    )

    assert result.exit_code == 7
    assert result.stderr_tail == "some stderr"
