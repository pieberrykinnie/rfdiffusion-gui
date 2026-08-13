"""Runner-specific exceptions. See business-rules.md sections 1, 3."""
from __future__ import annotations


class RunnerError(Exception):
    """Base class for every exception this package raises."""


class AnanasUnavailableError(RunnerError):
    """symmetry=auto was requested but the ananas binary is missing or not executable.

    Raised BEFORE any subprocess is spawned (business-rules.md section 3). The message covers all
    three required elements: what was requested and why it can't proceed, that none/cyclic/
    dihedral all work fine, and how to enable auto later.
    """

    def __init__(self, ananas_bin: str) -> None:
        self.ananas_bin = ananas_bin
        super().__init__(
            f"symmetry='auto' was requested but the AnAnaS binary is not present or not "
            f"executable at {ananas_bin}. symmetry='none', 'cyclic', or 'dihedral' with an "
            f"explicit order all work without it. To enable 'auto', set RFD_ANANAS_URL before "
            f"staging weights, or place the binary manually at that path (see "
            f"scripts/stage-weights.sh)."
        )


class NoCompletedBackboneError(RunnerError):
    """--stage validate was invoked against a RunRecord with no completed backbone stage."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"no completed backbone stage in {run_id}")


class SymmetryDetectionError(RunnerError):
    """AnAnaS ran but its output could not be parsed as a valid detection result.

    Distinct from "ran, found nothing" (represented by detect_symmetry returning None, not an
    error -- business-rules.md section 1). Replaces the notebook's bare `except:` (TD-8): a
    genuine parse/JSON failure must not be silently conflated with a legitimate negative result.
    """
