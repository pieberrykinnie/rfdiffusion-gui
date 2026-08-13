"""Publishes the current live-progress frame to persistent storage.

Resolves the FR-17 / G-11 conflict (Application Design DD-6): per-step churn stays on node-local
scratch (dump_dir), and only the LATEST frame is atomically published to the persistent,
bind-mounted run directory as a single small file overwritten in place -- the login node's web app
can see this file; it cannot see $TMPDIR on the compute node.

Uses the same same-directory-temp-file-plus-os.replace pattern as rfd_core.storage.write_json_atomic
(that helper is pydantic-model-specific; current_frame.pdb is raw PDB text, so this module
replicates the same atomicity technique for bytes).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional


class FramePublisher:
    def __init__(self, run_dir: Path, every_n: int = 5, enabled: bool = True) -> None:
        self.run_dir = Path(run_dir)
        self.every_n = every_n
        self.enabled = enabled

    def maybe_publish(self, step: int, frame: Path) -> Optional[Path]:
        # Step counting (the caller's progress reporting) continues regardless of `enabled` --
        # this only gates whether a frame is ever written (component-methods.md C-15).
        if not self.enabled:
            return None
        if step % self.every_n != 0:
            return None

        target = self.run_dir / "current_frame.pdb"
        data = Path(frame).read_bytes()

        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        return target
