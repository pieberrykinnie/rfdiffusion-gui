"""C-24 against real SQLite files in tmp_path -- no mocks."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from rfd_core import StageState

from rfd_web.persistence.repository import RunRepository
from rfd_web.persistence.schema import SCHEMA_VERSION, connect, read_schema_version
from rfd_web.status import RunStatus

from conftest import make_record


def test_pragmas_and_schema_version_are_really_applied(repository):
    conn = connect(repository.db_path)
    try:
        assert read_schema_version(conn) == SCHEMA_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_create_then_get_round_trips(repository, layout):
    record = make_record(layout.run_dir("a"), run_id="a")
    repository.create(record)
    summary = repository.get("a")
    assert summary is not None
    assert summary.name == "a"
    assert summary.status is RunStatus.QUEUED
    assert summary.contigs == record.request.contigs
    assert summary.partition == "gpu"
    assert summary.terminal is False


def test_get_returns_none_for_an_unknown_run(repository):
    assert repository.get("nope") is None


def test_upsert_is_idempotent_and_refreshes(repository, layout):
    record = make_record(layout.run_dir("a"), run_id="a")
    repository.upsert_from_record(record, RunStatus.QUEUED)
    record.backbone_state = StageState.RUNNING
    record.slurm_job_id = "999"
    repository.upsert_from_record(record, RunStatus.RUNNING)

    assert len(repository.list()) == 1
    summary = repository.get("a")
    assert summary.status is RunStatus.RUNNING
    assert summary.slurm_job_id == "999"
    assert summary.backbone_state is StageState.RUNNING


def test_list_is_newest_first_and_honours_limit(repository, layout):
    base = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    for i in range(5):
        record = make_record(
            layout.run_dir("r{0}".format(i)),
            run_id="r{0}".format(i),
            created_at=base + timedelta(minutes=i),
        )
        repository.create(record)
    listed = repository.list(limit=3)
    assert [s.run_id for s in listed] == ["r4", "r3", "r2"]


def test_mark_terminal_sets_the_short_circuit_flag(repository, layout):
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    repository.mark_terminal("a", RunStatus.COMPLETED, slurm_state="COMPLETED", exit_code=0)
    summary = repository.get("a")
    assert summary.terminal is True
    assert summary.status is RunStatus.COMPLETED
    assert summary.slurm_state == "COMPLETED"
    assert summary.exit_code == 0


def test_live_job_ids_returns_only_non_terminal_indexed_jobs(repository, layout):
    for run_id, job_id, terminal in (("a", "1", False), ("b", "2", True), ("c", None, False)):
        record = make_record(layout.run_dir(run_id), run_id=run_id)
        record.slurm_job_id = job_id
        repository.upsert_from_record(record, RunStatus.QUEUED)
        if terminal:
            repository.mark_terminal(run_id, RunStatus.COMPLETED)
    assert repository.live_job_ids() == ["1"]


def test_job_id_history_round_trips_as_json(repository, layout):
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    repository.append_job_id("a", "100")
    repository.append_job_id("a", "101")
    repository.append_job_id("a", "101")  # idempotent
    assert repository.get("a").job_id_history == ("100", "101")

    conn = connect(repository.db_path)
    try:
        raw = conn.execute("SELECT job_id_history FROM runs WHERE run_id='a'").fetchone()[0]
    finally:
        conn.close()
    assert json.loads(raw) == ["100", "101"]


def test_index_only_columns_survive_a_reconciliation_upsert(repository, layout):
    """A rebuild from disk must not erase what only the index knows."""
    record = make_record(layout.run_dir("a"), run_id="a")
    repository.create(record)
    repository.append_job_id("a", "100")
    repository.mark_cancel_requested("a")

    repository.upsert_from_record(record, RunStatus.RUNNING)

    summary = repository.get("a")
    assert summary.job_id_history == ("100",)
    assert summary.cancel_requested_at is not None


def test_mark_missing_flags_rather_than_deletes(repository, layout):
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    repository.mark_missing("a")
    summary = repository.get("a")
    assert summary is not None, "the row must survive -- BR-19"
    assert summary.missing is True


def test_update_state_refuses_unknown_columns(repository, layout):
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    with pytest.raises(ValueError):
        repository.update_state("a", nonexistent_column=1)
    with pytest.raises(ValueError):
        repository.update_state("a", **{"status = 'x'; DROP TABLE runs; --": 1})


def test_concurrent_reader_is_not_blocked_by_an_open_writer(repository, layout):
    """WAL plus a busy timeout is what keeps an HTMX poll from failing with
    'database is locked' while a submission commits (BR-21)."""
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    writer = connect(repository.db_path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE runs SET name = 'changed' WHERE run_id = 'a'")
        # Under WAL the reader sees the pre-commit snapshot rather than erroring.
        assert repository.get("a").name == "a"
        writer.commit()
    finally:
        writer.close()
    assert repository.get("a").name == "changed"


def test_repository_can_be_constructed_twice_over_the_same_file(layout):
    RunRepository(layout.database_path)
    RunRepository(layout.database_path)  # CREATE TABLE IF NOT EXISTS -- must not raise


def test_a_corrupt_history_column_does_not_break_reads(repository, layout):
    repository.create(make_record(layout.run_dir("a"), run_id="a"))
    conn = connect(repository.db_path)
    try:
        conn.execute("UPDATE runs SET job_id_history = 'not json' WHERE run_id = 'a'")
        conn.commit()
    finally:
        conn.close()
    assert repository.get("a").job_id_history == ()
