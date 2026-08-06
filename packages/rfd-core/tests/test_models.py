from datetime import datetime, timezone

from rfd_core.models import (
    DesignRequest,
    ProgressState,
    RunOutputs,
    RunRecord,
    StageState,
)
from rfd_core.symmetry import SymmetryKind


def make_request(**overrides):
    defaults = dict(
        name="test-run",
        contigs="100",
        partition="gpu",
        walltime="0-08:00:00",
    )
    defaults.update(overrides)
    return DesignRequest(**defaults)


class TestDesignRequestDefaults:
    def test_minimal_construction(self):
        req = make_request()
        assert req.iterations == 50
        assert req.num_designs == 1
        assert req.symmetry == SymmetryKind.NONE
        assert req.live_preview is True
        assert req.rm_aa == "C"

    def test_symmetry_accepts_string_value(self):
        # pydantic coerces "cyclic" -> SymmetryKind.CYCLIC via the str Enum.
        req = make_request(symmetry="cyclic")
        assert req.symmetry == SymmetryKind.CYCLIC


class TestStageStateStringEquality:
    def test_compares_equal_to_its_string_value(self):
        # Python 3.9: class StageState(str, Enum) -- must behave like a str.
        assert StageState.PENDING == "pending"
        assert StageState.RUNNING.value == "running"


class TestRunRecordRoundTrip:
    def test_json_round_trip_preserves_fields(self, tmp_path):
        req = make_request(contigs="A163-181")
        record = RunRecord(
            run_id="r1",
            name="test-run",
            run_dir=str(tmp_path),
            created_at=datetime.now(timezone.utc),
            request=req,
            backbone_state=StageState.RUNNING,
        )
        record.save(tmp_path)

        loaded = RunRecord.load(tmp_path)
        assert loaded.run_id == "r1"
        assert loaded.request.contigs == "A163-181"
        assert loaded.backbone_state == StageState.RUNNING
        assert loaded.schema_version == 1

    def test_load_raises_when_no_run_json(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            RunRecord.load(tmp_path)

    def test_optional_fields_default_to_none(self):
        req = make_request()
        record = RunRecord(
            run_id="r1",
            name="test-run",
            run_dir="/tmp/r1",
            created_at=datetime.now(timezone.utc),
            request=req,
        )
        assert record.mode is None
        assert record.normalised_contigs is None
        assert record.copies is None
        assert record.outputs is None


class TestRunOutputs:
    def test_lists_default_to_empty_not_none(self):
        outputs = RunOutputs()
        assert outputs.backbone_pdbs == []
        assert outputs.trajectory_pdbs == []


class TestProgressStateRoundTrip:
    def test_json_round_trip(self, tmp_path):
        state = ProgressState(
            stage="backbone",
            design_index=0,
            total_designs=4,
            step=12,
            total_steps=50,
            updated_at=datetime.now(timezone.utc),
        )
        state.save(tmp_path)

        loaded = ProgressState.load(tmp_path)
        assert loaded is not None
        assert loaded.step == 12
        assert loaded.total_steps == 50

    def test_load_returns_none_when_absent(self, tmp_path):
        assert ProgressState.load(tmp_path) is None
