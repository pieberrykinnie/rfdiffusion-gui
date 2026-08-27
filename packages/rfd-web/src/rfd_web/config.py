"""Login-node configuration, read from environment variables.

Mirrors rfd_core.paths.PathLayout.from_env() and rfd_runner.config.RunnerConfig.from_env():
plain os.environ reads, no new config file format. See env.example for every variable
below, its default, and why that default was chosen; domain-entities.md section 7 is the
design-side reference.

PathLayout covers weights/image/output-root/database. WebConfig covers everything else the
login node needs, including the two paths the job script interpolates that PathLayout does
not carry (RFD_PROJECT_ROOT and the Apptainer cache dir).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        # A typo'd interval must not take the app down on import. The default is
        # always safe; the wrong value is not worth a crash on a login node.
        return default


@dataclass(frozen=True)
class WebConfig:
    # --- polling and freshness (NFR-15, NFR-16) ---
    status_poll_seconds: int
    slurm_timeout_seconds: int
    partition_cache_seconds: int
    progress_stale_seconds: int
    log_tail_lines: int

    # --- partition compatibility annotation (FR-6a, Q3=A) ---
    incompatible_partitions: Tuple[str, ...]

    # --- submission defaults (FR-6, NFR-8, G-7, G-8) ---
    default_partition: str
    default_account: Optional[str]
    default_gpus: int
    default_cpus_per_task: int
    default_mem_per_cpu: str
    default_walltime: str

    # --- paths the job script needs that PathLayout does not carry ---
    project_root: Path
    apptainer_cachedir: Path

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "WebConfig":
        e = env if env is not None else os.environ
        home = Path(e.get("HOME", str(Path.home())))

        raw_incompatible = e.get("RFD_INCOMPATIBLE_PARTITIONS", "lgpu")
        incompatible = tuple(
            part.strip() for part in raw_incompatible.split(",") if part.strip()
        )

        account = e.get("RFD_DEFAULT_ACCOUNT", "").strip()

        auto_root = Path(__file__).resolve().parents[3]
        default_project_root = auto_root if (auto_root / "packages").exists() else home / "rfdiffusion-gui"

        return cls(
            status_poll_seconds=_int(e, "RFD_STATUS_POLL_SECONDS", 5),
            slurm_timeout_seconds=_int(e, "RFD_SLURM_TIMEOUT_SECONDS", 30),
            partition_cache_seconds=_int(e, "RFD_PARTITION_CACHE_SECONDS", 300),
            progress_stale_seconds=_int(e, "RFD_PROGRESS_STALE_SECONDS", 120),
            log_tail_lines=_int(e, "RFD_LOG_TAIL_LINES", 50),
            incompatible_partitions=incompatible,
            default_partition=e.get("RFD_DEFAULT_PARTITION", "gpu"),
            # Empty string means "omit --account entirely", which env.example
            # documents; None keeps that distinct from an account literally named "".
            default_account=account or None,
            default_gpus=_int(e, "RFD_DEFAULT_GPUS", 1),
            default_cpus_per_task=_int(e, "RFD_DEFAULT_CPUS_PER_TASK", 6),
            default_mem_per_cpu=e.get("RFD_DEFAULT_MEM_PER_CPU", "6000M"),
            default_walltime=e.get("RFD_DEFAULT_WALLTIME", "0-08:00:00"),
            project_root=Path(e.get("RFD_PROJECT_ROOT", str(default_project_root))),
            apptainer_cachedir=Path(
                e.get("APPTAINER_CACHEDIR", str(home / ".cache" / "apptainer"))
            ),
        )

    def is_compatible(self, partition_name: str) -> bool:
        return partition_name not in self.incompatible_partitions
