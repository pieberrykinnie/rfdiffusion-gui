"""Volatile progress reporting -- writes rfd_core's progress.json.

See component-methods.md C-16 and Application Design DD-4/Q4=A: progress.json is deliberately
separate from run.json, so a partial or stale progress write can never corrupt the durable run
record. ProgressReporter.update_step is called every step, unconditionally, by
InferenceExecutor's on_step hook -- this is what keeps the progress bar smooth even when live
preview (FramePublisher) is off.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rfd_core import ProgressState


class ProgressReporter:
    def __init__(self, run_dir: Path, total_designs: int = 1) -> None:
        self.run_dir = Path(run_dir)
        self._stage = "backbone"
        self._design_index = 0
        self._total_designs = total_designs
        self._step = 0
        self._total_steps = 0
        self._frame_path: Optional[Path] = None

    def update_step(self, stage: str, design_index: int, step: int, total: int) -> None:
        self._stage = stage
        self._design_index = design_index
        self._step = step
        self._total_steps = total
        self._save()

    def set_frame(self, frame_path: Path) -> None:
        self._frame_path = Path(frame_path)
        self._save()

    def set_stage(self, stage: str) -> None:
        self._stage = stage
        self._save()

    def _save(self) -> None:
        state = ProgressState(
            stage=self._stage,
            design_index=self._design_index,
            total_designs=self._total_designs,
            step=self._step,
            total_steps=self._total_steps,
            frame_path=str(self._frame_path) if self._frame_path is not None else None,
            updated_at=datetime.now(timezone.utc),
        )
        state.save(self.run_dir)
