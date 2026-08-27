"""C-21 SlurmAdapter -- the ONLY place in rfd-web that spawns a subprocess.

Every command is an argument list with shell=False (NFR-11), stdout and stderr captured
separately, exit codes checked (NFR-13), under an explicit timeout so a wedged controller
cannot pin a login-node process (BR-22, NFR-15).

Query order is squeue first, sacct second (services.md): the live queue is cheap and
authoritative while the job exists; sacct is the only source once it does not.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

try:  # pragma: no cover - Protocol is stdlib from 3.8; runtime_checkable from 3.8
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

from ..errors import SlurmSubmitError, SlurmUnavailable
from .partitions import PartitionInfo
from .states import JobStatus, SlurmState, map_state, normalise_state_word, parse_exit_code

#: squeue exits non-zero for an unknown job id rather than printing nothing. That is
#: NOT an unavailable controller -- it is the ordinary "job has left the queue" case,
#: and treating it as a failure would send every finished run down the BR-4 stale path.
_UNKNOWN_JOB_MARKERS = ("invalid job id", "invalid job", "no job")


@runtime_checkable
class SlurmAdapter(Protocol):
    """The seam NFR-18 requires: everything Slurm-shaped is behind this."""

    def submit(self, script: Path, cwd: Path) -> str:
        """Submit `script`, returning the job id. Raises SlurmSubmitError on rejection."""
        ...

    def status(self, job_id: str) -> JobStatus:
        """Current status. Raises SlurmUnavailable if Slurm cannot be reached."""
        ...

    def cancel(self, job_id: str) -> None:
        """Cancel the job. Cancelling an already-finished job is a no-op (BR-11)."""
        ...

    def partitions(self) -> List[PartitionInfo]:
        """Raw partition rows from sinfo, one per partition/node-state group."""
        ...


class _Completed:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CliSlurmAdapter:
    """Real adapter: shells out to the Slurm client binaries on PATH."""

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    # -- plumbing ---------------------------------------------------------------

    def _run(self, argv: Sequence[str], cwd: Optional[Path] = None) -> _Completed:
        try:
            proc = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=self.timeout_seconds,
                # shell=False is the default and is never overridden anywhere in this
                # package (NFR-11). tests/test_adapter.py asserts it.
            )
        except FileNotFoundError as exc:
            raise SlurmUnavailable(
                "{0} not found on PATH -- is this a Grex login node?".format(argv[0])
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SlurmUnavailable(
                "{0} timed out after {1}s".format(argv[0], self.timeout_seconds)
            ) from exc
        except OSError as exc:
            raise SlurmUnavailable("could not run {0}: {1}".format(argv[0], exc)) from exc
        return _Completed(proc.returncode, proc.stdout or "", proc.stderr or "")

    @staticmethod
    def _mentions_unknown_job(stderr: str) -> bool:
        low = stderr.lower()
        return any(marker in low for marker in _UNKNOWN_JOB_MARKERS)

    # -- SlurmAdapter -----------------------------------------------------------

    def submit(self, script: Path, cwd: Path) -> str:
        # --parsable so stdout is the bare job id. sbatch also writes lines like
        # "sbatch: WARNING -- Using default account: def-cardona" (seen throughout M1);
        # those go to stderr and never have to be parsed out.
        result = self._run(["sbatch", "--parsable", str(script)], cwd=cwd)
        if result.returncode != 0:
            raise SlurmSubmitError(
                "sbatch exited {0}".format(result.returncode), stderr=result.stderr.strip()
            )
        # "12345" or "12345;cluster"
        job_id = result.stdout.strip().split(";")[0].strip()
        if not job_id.isdigit():
            raise SlurmSubmitError(
                "could not read a job id from sbatch output: {0!r}".format(
                    result.stdout.strip()
                ),
                stderr=result.stderr.strip(),
            )
        return job_id

    def status(self, job_id: str) -> JobStatus:
        live = self._squeue(job_id)
        if live is not None:
            return live
        return self._sacct(job_id)

    def _squeue(self, job_id: str) -> Optional[JobStatus]:
        result = self._run(["squeue", "-h", "-j", str(job_id), "-o", "%T|%r"])
        if result.returncode != 0:
            if self._mentions_unknown_job(result.stderr):
                return None  # left the queue; sacct is the next stop
            raise SlurmUnavailable("squeue exited {0}: {1}".format(result.returncode, result.stderr.strip()))
        line = result.stdout.strip()
        if not line:
            return None
        first = line.splitlines()[0]
        parts = first.split("|")
        state = map_state(parts[0])
        reason = parts[1].strip() if len(parts) > 1 and parts[1].strip() not in ("", "None") else None
        return JobStatus(state=state, reason=reason)

    def _sacct(self, job_id: str) -> JobStatus:
        # -X keeps allocation rows only. Without it every job also yields .batch and
        # .extern rows (visible in M1's own sacct output), which are not separate jobs.
        result = self._run(
            ["sacct", "-n", "-P", "-X", "-j", str(job_id), "-o", "State,ExitCode"]
        )
        if result.returncode != 0:
            if self._mentions_unknown_job(result.stderr):
                return JobStatus(state=SlurmState.UNKNOWN, known=False)
            raise SlurmUnavailable("sacct exited {0}: {1}".format(result.returncode, result.stderr.strip()))

        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        if not lines:
            # Both queries ran and Slurm has no record: BR-4's "absent", not "unreachable".
            return JobStatus(state=SlurmState.UNKNOWN, known=False)

        fields = lines[0].split("|")
        raw_state = fields[0] if fields else ""
        exit_code, signal = parse_exit_code(fields[1] if len(fields) > 1 else "")
        return JobStatus(
            state=map_state(raw_state),
            exit_code=exit_code,
            signal=signal,
            reason=normalise_state_word(raw_state) or None,
        )

    def cancel(self, job_id: str) -> None:
        result = self._run(["scancel", str(job_id)])
        if result.returncode == 0:
            return
        if self._mentions_unknown_job(result.stderr):
            # BR-11: the user asked for the job to stop, and it has stopped.
            return
        raise SlurmUnavailable(
            "scancel exited {0}: {1}".format(result.returncode, result.stderr.strip())
        )

    def partitions(self) -> List[PartitionInfo]:
        # %P (not %R) so the default partition keeps its trailing '*'.
        result = self._run(["sinfo", "-h", "-o", "%P|%G|%l|%a"])
        if result.returncode != 0:
            raise SlurmUnavailable(
                "sinfo exited {0}: {1}".format(result.returncode, result.stderr.strip())
            )
        return [
            info
            for info in (self._parse_sinfo_row(line) for line in result.stdout.splitlines())
            if info is not None
        ]

    @staticmethod
    def _parse_sinfo_row(line: str) -> Optional[PartitionInfo]:
        if not line.strip():
            return None
        fields = line.split("|")
        if len(fields) < 4:
            return None
        raw_name, gres, timelimit, avail = (f.strip() for f in fields[:4])
        is_default = raw_name.endswith("*")
        name = raw_name.rstrip("*")
        if not name:
            return None
        return PartitionInfo(
            name=name,
            has_gpu="gpu" in gres.lower() and gres.strip() not in ("", "(null)"),
            # "infinite" is a real sinfo value and is not a duration; None says
            # "no limit" rather than pretending to be one.
            max_walltime=None if timelimit.lower() in ("infinite", "", "n/a") else timelimit,
            is_default=is_default,
            available=avail.lower() == "up",
        )
