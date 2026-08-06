import os

import pytest
from pydantic import BaseModel

from rfd_core.storage import read_json, write_json_atomic


class Sample(BaseModel):
    value: int
    label: str = "x"


class TestWriteAndRead:
    def test_round_trip(self, tmp_path):
        p = tmp_path / "sample.json"
        write_json_atomic(p, Sample(value=42))
        loaded = read_json(p, Sample)
        assert loaded is not None
        assert loaded.value == 42

    def test_creates_parent_directories(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "sample.json"
        write_json_atomic(p, Sample(value=1))
        assert p.exists()

    def test_no_leftover_temp_files_after_success(self, tmp_path):
        p = tmp_path / "sample.json"
        write_json_atomic(p, Sample(value=1))
        remaining = list(tmp_path.iterdir())
        assert remaining == [p]

    def test_overwrite_replaces_content(self, tmp_path):
        p = tmp_path / "sample.json"
        write_json_atomic(p, Sample(value=1))
        write_json_atomic(p, Sample(value=2))
        assert read_json(p, Sample).value == 2


class TestReadReturnsNoneRatherThanRaising:
    def test_missing_file(self, tmp_path):
        assert read_json(tmp_path / "nope.json", Sample) is None

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert read_json(p, Sample) is None

    def test_whitespace_only_file(self, tmp_path):
        p = tmp_path / "ws.json"
        p.write_text("   \n  ")
        assert read_json(p, Sample) is None

    def test_corrupt_json(self, tmp_path):
        p = tmp_path / "corrupt.json"
        p.write_text("{not valid json")
        assert read_json(p, Sample) is None

    def test_valid_json_wrong_schema(self, tmp_path):
        p = tmp_path / "wrong.json"
        p.write_text('{"totally": "unrelated"}')
        # `value` is required and missing -> pydantic validation error -> None
        assert read_json(p, Sample) is None


class TestAtomicityUnderFailure:
    """These target the code's two distinct failure windows separately:
    before any temp file exists (model_dump_json raises), and after the temp
    file is written but before/during the atomic rename (os.replace raises).
    A mock that fails 'mid-write' by patching model_dump_json never actually
    reaches the cleanup path, since that call happens before tempfile.mkstemp
    -- caught by coverage, not by the test passing (it passed vacuously)."""

    def test_no_temp_file_created_when_serialisation_fails_before_mkstemp(
        self, tmp_path, monkeypatch
    ):
        p = tmp_path / "sample.json"

        def boom(self, **kwargs):
            raise RuntimeError("simulated serialisation failure")

        monkeypatch.setattr(Sample, "model_dump_json", boom)
        with pytest.raises(RuntimeError):
            write_json_atomic(p, Sample(value=1))

        assert not p.exists()
        assert list(tmp_path.iterdir()) == []

    def test_temp_file_cleaned_up_when_replace_fails(self, tmp_path, monkeypatch):
        p = tmp_path / "sample.json"

        def boom_replace(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", boom_replace)
        with pytest.raises(OSError):
            write_json_atomic(p, Sample(value=1))

        # The temp file genuinely existed (write succeeded) and must not
        # survive the failed replace.
        assert not p.exists()
        assert list(tmp_path.iterdir()) == []

    def test_existing_file_untouched_when_replace_fails(self, tmp_path, monkeypatch):
        p = tmp_path / "sample.json"
        write_json_atomic(p, Sample(value=1))

        def boom_replace(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", boom_replace)
        with pytest.raises(OSError):
            write_json_atomic(p, Sample(value=2))

        # A reader must never see a torn write: the old value survives intact.
        assert read_json(p, Sample).value == 1

    def test_original_error_preserved_even_if_cleanup_unlink_also_fails(
        self, tmp_path, monkeypatch
    ):
        p = tmp_path / "sample.json"

        def boom_replace(src, dst):
            raise OSError("simulated replace failure")

        def boom_unlink(path):
            raise OSError("simulated unlink failure during cleanup")

        monkeypatch.setattr(os, "replace", boom_replace)
        monkeypatch.setattr(os, "unlink", boom_unlink)

        # The cleanup attempt's own failure must be swallowed -- the caller
        # sees the ORIGINAL error (replace), never the secondary one (unlink).
        with pytest.raises(OSError, match="simulated replace failure"):
            write_json_atomic(p, Sample(value=1))
