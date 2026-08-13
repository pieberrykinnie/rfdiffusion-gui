import json

import pytest

from rfd_runner import _colabdesign
from rfd_runner.errors import AnanasUnavailableError, SymmetryDetectionError
from rfd_runner.symmetry_detector import SymmetryDetector

# A canonical PDB ATOM line (the textbook example) -- column positions match exactly what
# symmetry_detector.py slices: chain at [21:22], x/y/z at [30:38]/[38:46]/[46:54].
_ATOM_LINE = "ATOM      1  N   ASP A   1      11.104  13.207   8.972  1.00  0.00           N"
_PDB_STR = f"{_ATOM_LINE}\nTER\n"


def _executable(tmp_path, name="ananas"):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n")
    p.chmod(0o755)
    return p


def test_missing_ananas_raises_before_run_cmd(tmp_path):
    calls = []
    with pytest.raises(AnanasUnavailableError) as exc_info:
        SymmetryDetector().detect_symmetry(
            _PDB_STR, tmp_path, ananas_bin=tmp_path / "no-such-binary", run_cmd=calls.append
        )
    assert calls == []
    msg = str(exc_info.value)
    assert "auto" in msg
    assert "none" in msg and "cyclic" in msg and "dihedral" in msg
    assert "RFD_ANANAS_URL" in msg


def test_non_executable_ananas_raises_before_run_cmd(tmp_path):
    non_exec = tmp_path / "ananas"
    non_exec.write_text("#!/bin/sh\n")  # no chmod +x
    calls = []
    with pytest.raises(AnanasUnavailableError):
        SymmetryDetector().detect_symmetry(
            _PDB_STR, tmp_path, ananas_bin=non_exec, run_cmd=calls.append
        )
    assert calls == []


def test_well_formed_output_parsed_into_detection(tmp_path, monkeypatch):
    ananas_bin = _executable(tmp_path)

    def fake_sym_it(x, center, axis1, axis2=None):
        return [c + 1.0 for c in x]

    monkeypatch.setattr(_colabdesign, "sym_it", fake_sym_it)

    def fake_run_cmd(argv):
        out_filename = tmp_path / "ananas.json"
        payload = [
            {"Average_RMSD": 0.42, "transforms": [{"CENTER": [0, 0, 0], "AXIS": [0, 0, 1]}]},
            {"AU": {"group": "c2", "chain names": ["A"]}},
        ]
        out_filename.write_text(json.dumps(payload))

    detection = SymmetryDetector().detect_symmetry(
        _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
    )

    assert detection is not None
    assert detection.group == "c2"
    assert detection.rmsd == 0.42
    assert "ATOM" in detection.asymmetric_unit_pdb_str
    assert "TER" in detection.asymmetric_unit_pdb_str


def test_no_output_file_returns_none(tmp_path):
    ananas_bin = _executable(tmp_path)

    def fake_run_cmd(argv):
        pass  # ananas ran but wrote nothing

    result = SymmetryDetector().detect_symmetry(
        _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
    )
    assert result is None


def test_empty_result_list_returns_none_not_error(tmp_path):
    ananas_bin = _executable(tmp_path)

    def fake_run_cmd(argv):
        (tmp_path / "ananas.json").write_text("[]")

    result = SymmetryDetector().detect_symmetry(
        _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
    )
    assert result is None


def test_invalid_json_raises_symmetry_detection_error(tmp_path):
    ananas_bin = _executable(tmp_path)

    def fake_run_cmd(argv):
        (tmp_path / "ananas.json").write_text("{not valid json")

    with pytest.raises(SymmetryDetectionError):
        SymmetryDetector().detect_symmetry(
            _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
        )


def test_falsy_group_treated_as_found_nothing(tmp_path):
    ananas_bin = _executable(tmp_path)

    def fake_run_cmd(argv):
        payload = [
            {"Average_RMSD": 0.1, "transforms": []},
            {"AU": {"group": "", "chain names": []}},
        ]
        (tmp_path / "ananas.json").write_text(json.dumps(payload))

    result = SymmetryDetector().detect_symmetry(
        _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
    )
    assert result is None


def test_dihedral_group_uses_two_axis_sym_it(tmp_path, monkeypatch):
    ananas_bin = _executable(tmp_path)
    sym_it_calls = []

    def fake_sym_it(x, center, axis1, axis2=None):
        sym_it_calls.append((axis1, axis2))
        return x

    monkeypatch.setattr(_colabdesign, "sym_it", fake_sym_it)

    def fake_run_cmd(argv):
        payload = [
            {
                "Average_RMSD": 0.3,
                "transforms": [{"CENTER": [0, 0, 0], "AXIS": "axis0"}, {"AXIS": "axis1"}],
            },
            {"AU": {"group": "d2", "chain names": ["A"]}},
        ]
        (tmp_path / "ananas.json").write_text(json.dumps(payload))

    detection = SymmetryDetector().detect_symmetry(
        _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
    )

    assert detection is not None
    assert detection.group == "d2"
    # Notebook line 133-134: dihedral uses sym_it(x, C, A[1], A[0]) -- axes reversed vs cyclic.
    assert sym_it_calls == [("axis1", "axis0")]


def test_default_run_cmd_invokes_subprocess_run(monkeypatch):
    from rfd_runner import symmetry_detector as symmetry_detector_module

    calls = []
    monkeypatch.setattr(
        symmetry_detector_module.subprocess,
        "run",
        lambda argv, check: calls.append((argv, check)),
    )

    symmetry_detector_module._default_run_cmd(["ananas", "in.pdb"])

    assert calls == [(["ananas", "in.pdb"], True)]


def test_malformed_but_valid_json_raises_symmetry_detection_error(tmp_path):
    ananas_bin = _executable(tmp_path)

    def fake_run_cmd(argv):
        # Valid JSON, but missing the "AU" key entirely -- structurally malformed, must NOT be
        # conflated with the legitimate "found nothing" case above.
        (tmp_path / "ananas.json").write_text(json.dumps([{"Average_RMSD": 0.1}, {}]))

    with pytest.raises(SymmetryDetectionError):
        SymmetryDetector().detect_symmetry(
            _PDB_STR, tmp_path, ananas_bin=ananas_bin, run_cmd=fake_run_cmd
        )
