"""Runner configuration, read from environment variables set by the container.

Mirrors rfd_core.paths.PathLayout's from_env() pattern: plain os.environ reads, no new config
file format. See domain-entities.md section 4 for RFD_STEP_TIMEOUT_SECONDS/RFD_POLL_INTERVAL_MS,
and containers/rfdiffusion.def's %environment block for RFD_FORK/RFD_MODELS/RFD_AF_PARAMS/
ANANAS_BIN, which are already exported there -- this module reads them rather than re-deriving.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RunnerConfig:
    step_timeout_seconds: int
    poll_interval_ms: int
    frame_every_n: int
    fork_root: Path
    models_dir: Path
    af_params_dir: Path
    ananas_bin: Path
    python_bin: Path

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> RunnerConfig:
        e = env if env is not None else os.environ
        return cls(
            step_timeout_seconds=int(e.get("RFD_STEP_TIMEOUT_SECONDS", "1800")),
            poll_interval_ms=int(e.get("RFD_POLL_INTERVAL_MS", "100")),
            frame_every_n=int(e.get("RFD_FRAME_EVERY_N", "5")),
            fork_root=Path(e.get("RFD_FORK", "/opt/RFdiffusion")),
            models_dir=Path(e.get("RFD_MODELS", "/opt/RFdiffusion/models")),
            af_params_dir=Path(e.get("RFD_AF_PARAMS", "/opt/weights/alphafold")),
            ananas_bin=Path(e.get("ANANAS_BIN", "/opt/weights/bin/ananas")),
            # Not currently overridden by any env var -- matches the container's fixed uv venv
            # path (confirmed against containers/rfdiffusion.def's %runscript).
            python_bin=Path("/app/RFdiffusion/.venv/bin/python"),
        )
