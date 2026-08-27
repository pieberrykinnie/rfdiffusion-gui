"""BR-7: the state map is total, and its fallback is UNKNOWN."""
from __future__ import annotations

import pytest

from rfd_web.slurm.states import (
    TERMINAL_STATES,
    JobStatus,
    SlurmState,
    map_state,
    normalise_state_word,
    parse_exit_code,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PENDING", SlurmState.PENDING),
        ("CONFIGURING", SlurmState.PENDING),
        ("SUSPENDED", SlurmState.PENDING),
        ("RUNNING", SlurmState.RUNNING),
        ("COMPLETING", SlurmState.RUNNING),
        ("COMPLETED", SlurmState.COMPLETED),
        ("FAILED", SlurmState.FAILED),
        ("NODE_FAIL", SlurmState.FAILED),
        ("OUT_OF_MEMORY", SlurmState.FAILED),
        ("PREEMPTED", SlurmState.FAILED),
        ("CANCELLED", SlurmState.CANCELLED),
        ("TIMEOUT", SlurmState.TIMEOUT),
    ],
)
def test_documented_states_map_as_specified(raw, expected):
    assert map_state(raw) == expected


def test_sacct_cancelled_by_uid_keeps_only_the_state_word():
    assert map_state("CANCELLED by 1234") == SlurmState.CANCELLED


def test_width_truncated_state_is_recovered():
    assert normalise_state_word("CANCELLED+") == "CANCELLED"
    assert map_state("CANCELLED+") == SlurmState.CANCELLED


@pytest.mark.parametrize("raw", ["", "   ", "SOMETHING_SLURM_ADDED_IN_25_11", "???"])
def test_unrecognised_states_are_unknown_never_completed_or_failed(raw):
    """A default of COMPLETED fabricates success; a default of FAILED cries wolf."""
    mapped = map_state(raw)
    assert mapped is SlurmState.UNKNOWN
    assert mapped is not SlurmState.COMPLETED
    assert mapped is not SlurmState.FAILED


def test_unknown_is_not_terminal():
    assert SlurmState.UNKNOWN not in TERMINAL_STATES
    assert TERMINAL_STATES == {
        SlurmState.COMPLETED,
        SlurmState.FAILED,
        SlurmState.CANCELLED,
        SlurmState.TIMEOUT,
    }
    assert not JobStatus(state=SlurmState.UNKNOWN).is_terminal
    assert JobStatus(state=SlurmState.COMPLETED).is_terminal


@pytest.mark.parametrize(
    "raw,expected",
    [("0:0", (0, 0)), ("1:0", (1, 0)), ("0:15", (0, 15)), ("137", (137, None))],
)
def test_exit_code_decoding(raw, expected):
    assert parse_exit_code(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "n/a", "x:y"])
def test_malformed_exit_code_is_none_not_an_exception(raw):
    assert parse_exit_code(raw) == (None, None)
