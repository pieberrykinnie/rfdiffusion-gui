"""C-25: log tail (Q7=A), REMARK 001 parsing, and path containment (BR-14)."""
from __future__ import annotations

import os
import time

import pytest

from rfd_web.errors import PathContainmentError
from rfd_web.persistence.reader import (
    LOG_TAIL_MAX_BYTES,
    RunDirectoryReader,
    best_design_index,
    current_frame,
    list_designs,
    log_tail,
    read_record,
    resolve_within,
)

from conftest import make_record


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    return d


def touch(path, text="", age_seconds=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(str(path), (stamp, stamp))
    return path


# -- log tail (Q7=A) ----------------------------------------------------------


def test_err_is_preferred_over_out(run_dir):
    touch(run_dir / "job-1.out", "stdout line\n")
    touch(run_dir / "job-1.err", "Traceback (most recent call last):\nModuleNotFoundError\n")
    assert "ModuleNotFoundError" in log_tail(run_dir)
    assert "stdout line" not in log_tail(run_dir)


def test_empty_err_falls_back_to_out(run_dir):
    touch(run_dir / "job-1.err", "")
    touch(run_dir / "job-1.out", "Job finished with exit code 127\n")
    assert "exit code 127" in log_tail(run_dir)


def test_missing_err_falls_back_to_out(run_dir):
    touch(run_dir / "job-1.out", "only stdout\n")
    assert "only stdout" in log_tail(run_dir)


def test_no_logs_at_all_is_empty_string_not_an_error(run_dir):
    assert log_tail(run_dir) == ""


def test_newest_job_log_wins_after_a_resubmission(run_dir):
    """A resubmission leaves the earlier job's logs in place (business-logic-model.md
    section 8), so newest-by-mtime is what makes log_tail point at the right attempt."""
    touch(run_dir / "job-100.err", "old failure\n", age_seconds=600)
    touch(run_dir / "job-101.err", "new failure\n")
    assert "new failure" in log_tail(run_dir)
    assert "old failure" not in log_tail(run_dir)


def test_line_limit_is_honoured(run_dir):
    touch(run_dir / "job-1.err", "".join("line {0}\n".format(i) for i in range(200)))
    tail = log_tail(run_dir, lines=5)
    assert tail.splitlines() == ["line {0}".format(i) for i in range(195, 200)]


def test_a_huge_log_is_read_bounded(run_dir):
    """NFR-15: a runaway log must not be pulled into a login-node process's memory."""
    big = "x" * (LOG_TAIL_MAX_BYTES * 3) + "\nTHE LAST LINE\n"
    touch(run_dir / "job-1.err", big)
    tail = log_tail(run_dir, lines=5)
    assert "THE LAST LINE" in tail
    assert len(tail.encode("utf-8")) <= LOG_TAIL_MAX_BYTES


def test_undecodable_bytes_do_not_raise(run_dir):
    (run_dir / "job-1.err").write_bytes(b"\xff\xfe bad bytes\nfine line\n")
    assert "fine line" in log_tail(run_dir)


# -- REMARK 001 (FR-24) -------------------------------------------------------


def test_best_design_index_is_parsed(run_dir):
    touch(
        run_dir / "smoke" / "best.pdb",
        "REMARK 001 BEST DESIGN 3\nATOM      1  N   MET A   1\n",
    )
    assert best_design_index(run_dir, "smoke") == 3


def test_best_design_index_is_found_without_knowing_the_name(run_dir):
    touch(run_dir / "smoke" / "best.pdb", "REMARK 001 BEST DESIGN 2\n")
    assert best_design_index(run_dir) == 2


def test_missing_best_pdb_is_none(run_dir):
    assert best_design_index(run_dir, "smoke") is None


def test_malformed_remark_is_none_not_an_exception(run_dir):
    touch(run_dir / "smoke" / "best.pdb", "REMARK 001 BEST DESIGN unknown\nATOM\n")
    assert best_design_index(run_dir, "smoke") is None


# -- frame availability (BR-6) ------------------------------------------------


def test_current_frame_is_decided_by_the_file(run_dir):
    assert current_frame(run_dir) is None
    touch(run_dir / "current_frame.pdb", "ATOM\n")
    assert current_frame(run_dir) is not None


# -- designs ------------------------------------------------------------------


def test_designs_are_listed_in_index_order_with_trajectories(run_dir):
    touch(run_dir / "smoke" / "smoke_0.pdb", "ATOM\n")
    touch(run_dir / "smoke" / "smoke_1.pdb", "ATOM\n")
    touch(run_dir / "smoke" / "traj" / "smoke_0_pX0_traj.pdb", "ATOM\n")
    designs = list_designs(run_dir, "smoke")
    assert [d.index for d in designs] == [0, 1]
    assert designs[0].trajectory_pdbs and not designs[1].trajectory_pdbs


def test_no_output_directory_is_an_empty_list(run_dir):
    assert list_designs(run_dir, "smoke") == []


# -- containment (BR-14) ------------------------------------------------------


@pytest.mark.parametrize("relative", ["../secrets", "../../etc/passwd", "/etc/passwd"])
def test_paths_escaping_the_run_directory_are_refused(run_dir, relative):
    with pytest.raises(PathContainmentError):
        resolve_within(run_dir, relative)


def test_a_symlink_pointing_outside_is_refused(run_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (run_dir / "link.txt").symlink_to(outside)
    with pytest.raises(PathContainmentError):
        resolve_within(run_dir, "link.txt")


def test_an_ordinary_nested_path_is_allowed(run_dir):
    touch(run_dir / "smoke" / "smoke_0.pdb", "ATOM\n")
    assert resolve_within(run_dir, "smoke/smoke_0.pdb").is_file()


# -- record reading -----------------------------------------------------------


def test_unreadable_run_json_is_none_not_an_exception(run_dir):
    (run_dir / "run.json").write_text("{not json")
    assert read_record(run_dir) is None


def test_absent_run_json_is_none(run_dir):
    assert read_record(run_dir) is None


def test_reader_object_binds_the_configured_tail_length(run_dir):
    touch(run_dir / "job-1.err", "".join("line {0}\n".format(i) for i in range(50)))
    reader = RunDirectoryReader(log_tail_lines=3)
    assert len(reader.log_tail(run_dir).splitlines()) == 3


def test_reader_round_trips_a_saved_record(run_dir):
    record = make_record(run_dir, run_id="smoke")
    record.save(run_dir)
    loaded = RunDirectoryReader().read_record(run_dir)
    assert loaded is not None and loaded.run_id == "smoke"
