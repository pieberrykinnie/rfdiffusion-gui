"""Exception types for the login-node half.

Principle inherited from rfd-core (its validation.py docstring): errors a user
needs to see and act on are VALUES -- ValidationOutcome, SubmissionOutcome,
RunView -- not exceptions. Exceptions here are reserved for an unusable
environment or a bug in the calling code.
"""
from __future__ import annotations

from typing import Optional


class SlurmError(Exception):
    """Base for everything that goes wrong talking to Slurm."""


class SlurmUnavailable(SlurmError):
    """A Slurm command failed, timed out, or is not on PATH.

    Deliberately distinct from JobStatus(state=UNKNOWN, known=False), which
    means the commands RAN and Slurm has no record of the job (business-rules.md
    BR-4). Collapsing the two turns a five-second controller hiccup into a UI
    that reports running jobs as lost.
    """


class SlurmSubmitError(SlurmError):
    """`sbatch` returned non-zero. Carries its stderr so BR-15 can show the user
    why, rather than only that nothing happened.
    """

    def __init__(self, message: str, stderr: Optional[str] = None) -> None:
        super().__init__(message)
        self.stderr = stderr or ""


class JobScriptError(Exception):
    """A value failed its whitelist during job-script generation (BR-12).

    Raised rather than sanitised-and-continued: a silently mangled --time is a
    job that dies three hours in.
    """


class PathContainmentError(Exception):
    """A resolved path escaped the run directory (BR-14)."""
