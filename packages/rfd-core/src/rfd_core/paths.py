"""Configurable filesystem locations (NFR-6). See env.example for the full
list of environment variables this reads and their defaults under $HOME.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Optional


class PathLayout:
    def __init__(
        self,
        weights_root: Path,
        image_path: Path,
        output_root: Path,
        database_path: Path,
    ) -> None:
        self.weights_root = weights_root
        self.image_path = image_path
        self.output_root = output_root
        self.database_path = database_path

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> PathLayout:
        e = env if env is not None else os.environ
        home = Path(e.get("HOME", str(Path.home())))
        return cls(
            weights_root=Path(e.get("RFD_WEIGHTS", str(home / "rfd-weights"))),
            image_path=Path(e.get("RFD_IMAGE", str(home / "rfd-images" / "rfdiffusion.sif"))),
            output_root=Path(e.get("RFD_OUTPUT_ROOT", str(home / "rfd-runs"))),
            database_path=Path(
                e.get("RFD_DB", str(home / ".local" / "share" / "rfdgui" / "runs.sqlite"))
            ),
        )

    def run_dir(self, run_id: str) -> Path:
        return self.output_root / run_id
