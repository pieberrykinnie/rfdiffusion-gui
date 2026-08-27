"""C-25 RunDirectoryReader -- reads the rfd-core contracts, outputs, and job logs.

Path containment (BR-14) is enforced HERE, at the bottom, rather than in U4's file
endpoint, so no future route can be written that bypasses it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rfd_core import ProgressState, RunRecord

from ..errors import PathContainmentError

#: Cap on how much of a log file is read from the end. FR-19 wants the tail; a runaway
#: log must not be pulled into a login-node process's memory (NFR-15).
LOG_TAIL_MAX_BYTES = 64 * 1024

#: RFdiffusion's best.pdb carries the chosen design index on a REMARK 001 line (FR-24).
_REMARK_001_RE = re.compile(r"^REMARK\s+001\b.*?(\d+)\s*$")


@dataclass(frozen=True)
class DesignOutputs:
    index: int
    backbone_pdb: Optional[Path] = None
    trajectory_pdbs: tuple = ()


def resolve_within(run_dir: Path, relative: str) -> Path:
    """Resolve `relative` inside `run_dir`, refusing anything that escapes (BR-14).

    Symlinks are resolved before the check, so a link pointing outside is refused too.
    """
    base = Path(run_dir).resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise PathContainmentError(
            "path {0!r} resolves outside the run directory {1}".format(relative, base)
        )
    return candidate


def read_record(run_dir: Path) -> Optional[RunRecord]:
    """The durable record, or None when absent/unreadable.

    None rather than raising: a half-written record from a crashed job is an expected
    state during reconciliation (BR-20), not an error.
    """
    try:
        return RunRecord.load(Path(run_dir))
    except (FileNotFoundError, OSError, ValueError):
        return None


def read_progress(run_dir: Path) -> Optional[ProgressState]:
    return ProgressState.load(Path(run_dir))


def current_frame(run_dir: Path) -> Optional[Path]:
    """The live preview frame, if it exists.

    Deliberately decided by the FILE, not by ProgressState.frame_path (BR-6): the M1
    pass proved the orchestrator never calls set_frame(), so frame_path stays null for
    an entire successful run while current_frame.pdb is published correctly.
    """
    path = Path(run_dir) / "current_frame.pdb"
    return path if path.is_file() else None


def list_designs(run_dir: Path, name: str) -> List[DesignOutputs]:
    """Per-design outputs, ordered by index, discovered from the run directory."""
    base = Path(run_dir)
    out_dir = base / name
    if not out_dir.is_dir():
        return []
    designs = {}
    for pdb in sorted(out_dir.glob("{0}_*.pdb".format(name))):
        stem = pdb.stem[len(name) + 1 :]
        if not stem.isdigit():
            continue
        designs[int(stem)] = pdb
    traj_dir = out_dir / "traj"
    trajectories = {}
    if traj_dir.is_dir():
        for traj in sorted(traj_dir.glob("{0}_*.pdb".format(name))):
            match = re.search(r"_(\d+)_", traj.name)
            if match:
                trajectories.setdefault(int(match.group(1)), []).append(traj)
    return [
        DesignOutputs(
            index=i,
            backbone_pdb=designs[i],
            trajectory_pdbs=tuple(sorted(trajectories.get(i, []))),
        )
        for i in sorted(designs)
    ]


def best_design_index(run_dir: Path, name: Optional[str] = None) -> Optional[int]:
    """Parse the design index out of best.pdb's REMARK 001 line (FR-24)."""
    base = Path(run_dir)
    candidates = []
    if name:
        candidates.append(base / name / "best.pdb")
    candidates.append(base / "best.pdb")
    candidates.extend(sorted(base.glob("*/best.pdb")))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with path.open("r") as fh:
                for line in fh:
                    if not line.startswith("REMARK"):
                        continue
                    match = _REMARK_001_RE.match(line.strip())
                    if match:
                        return int(match.group(1))
        except OSError:
            continue
    return None


def _newest(paths: List[Path]) -> Optional[Path]:
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def log_tail(run_dir: Path, lines: int = 50) -> str:
    """Tail of the job log (FR-19), per Q7=A.

    `.err` first, falling back to `.out` when `.err` is missing or empty -- the failure
    is nearly always in stderr, and the Python traceback that ended M1 rounds 1-6 always
    was. Newest-by-mtime matters because a resubmission leaves the earlier job's logs in
    place.
    """
    base = Path(run_dir)
    err = _newest(sorted(base.glob("job-*.err")))
    chosen: Optional[Path] = None
    if err is not None and err.stat().st_size > 0:
        chosen = err
    else:
        chosen = _newest(sorted(base.glob("job-*.out")))
    if chosen is None:
        return ""
    return _tail_of(chosen, lines)


def _tail_of(path: Path, lines: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            truncated = size > LOG_TAIL_MAX_BYTES
            if truncated:
                fh.seek(-LOG_TAIL_MAX_BYTES, os.SEEK_END)
            data = fh.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    if truncated:
        # Seeking to a byte offset lands mid-line, so the first line is a fragment.
        # Observed on real Grex data: a traceback tail began "nt call last):".
        # Dropping it costs one line of a 50-line tail and removes the only line that
        # could be misread as the start of the error.
        newline = text.find("\n")
        text = text[newline + 1 :] if newline != -1 else ""
    tail = text.splitlines()[-lines:] if lines > 0 else []
    return "\n".join(tail)


class RunDirectoryReader:
    """Object form, so services can be constructed with a fake reader.

    Methods mirror component-methods.md's C-25 free functions, which remain available
    at module level; this only binds the configured tail length.
    """

    def __init__(self, log_tail_lines: int = 50) -> None:
        self.log_tail_lines = log_tail_lines

    def read_record(self, run_dir: Path) -> Optional[RunRecord]:
        return read_record(run_dir)

    def read_progress(self, run_dir: Path) -> Optional[ProgressState]:
        return read_progress(run_dir)

    def current_frame(self, run_dir: Path) -> Optional[Path]:
        return current_frame(run_dir)

    def list_designs(self, run_dir: Path, name: str) -> List[DesignOutputs]:
        return list_designs(run_dir, name)

    def best_design_index(self, run_dir: Path, name: Optional[str] = None) -> Optional[int]:
        return best_design_index(run_dir, name)

    def log_tail(self, run_dir: Path, lines: Optional[int] = None) -> str:
        return log_tail(run_dir, self.log_tail_lines if lines is None else lines)

    def resolve_within(self, run_dir: Path, relative: str) -> Path:
        return resolve_within(run_dir, relative)
