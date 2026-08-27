"""C-22 PartitionDiscovery -- runtime discovery, never a hard-coded list (FR-6a).

Grex's own documentation is internally inconsistent about which GPU partitions exist
(the partitions page says gpu/lgpu; the batch-jobs page says gpu/stamps-b/livi-b/agro-b),
which is exactly why FR-6a forbids a list in code.

Q3=A: incompatible partitions are ANNOTATED, not filtered. The image is the user's to
replace, and a filter that silently removes a valid option is the same failure mode as
a hard-coded list. What is configurable (RFD_INCOMPATIBLE_PARTITIONS) describes the
IMAGE, not the cluster.

This module deliberately does not import adapter.py at runtime -- it only duck-types
`adapter.partitions()` -- so that adapter.py can import PartitionInfo from here without
a cycle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from ..config import WebConfig
from ..errors import SlurmUnavailable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .adapter import SlurmAdapter


@dataclass(frozen=True)
class PartitionInfo:
    name: str
    has_gpu: bool
    max_walltime: Optional[str]
    is_default: bool = False
    available: bool = True
    compatible: bool = True
    incompatible_reason: Optional[str] = None


#: Why a partition may be marked incompatible. Phrased as an image property, since
#: that is what it is -- env.example records the verified hardware behind the default:
#: the Phase 1 CUDA 11.6 image runs on gpu/stamps-b/livi-b (V100, sm_70) and
#: agpu/mcordgpu-b (A30, sm_80), but not on lgpu (L40s, sm_89).
INCOMPATIBLE_REASON = (
    "the configured image targets CUDA 11.6 (sm_70/sm_80); this partition's GPUs are "
    "newer and need a different image (see RFD_INCOMPATIBLE_PARTITIONS in env.example)"
)


@dataclass
class DiscoveryResult:
    partitions: List[PartitionInfo]
    warning: Optional[str] = None

    def __iter__(self):
        # Convenience so callers that only want the list can iterate the result
        # directly; the warning stays available for the form to render.
        return iter(self.partitions)


def annotate(
    partitions: List[PartitionInfo], config: WebConfig
) -> List[PartitionInfo]:
    """Mark partitions the configured image cannot use, without removing any."""
    out = []
    for p in partitions:
        if config.is_compatible(p.name):
            out.append(p)
        else:
            out.append(
                replace(p, compatible=False, incompatible_reason=INCOMPATIBLE_REASON)
            )
    return out


def discover_partitions(
    adapter: "SlurmAdapter", config: WebConfig, gpu_only: bool = True
) -> DiscoveryResult:
    """Discover partitions via the adapter (sinfo), de-duplicate, and annotate.

    Degradation is deliberate: if sinfo is unavailable the result is an empty list plus
    a warning, and the caller falls back to a free-text partition field pre-filled from
    RFD_DEFAULT_PARTITION. Discovery failing must never block submission.
    """
    try:
        raw = adapter.partitions()
    except SlurmUnavailable as exc:
        return DiscoveryResult(
            partitions=[],
            warning=(
                "could not discover partitions from Slurm ({0}); enter a partition name "
                "manually".format(exc)
            ),
        )

    seen = set()
    unique: List[PartitionInfo] = []
    for p in raw:
        # sinfo emits one row per partition/node-state group, so a partition with
        # both idle and allocated nodes appears more than once.
        if p.name in seen:
            continue
        if gpu_only and not p.has_gpu:
            continue
        seen.add(p.name)
        unique.append(p)

    return DiscoveryResult(partitions=annotate(unique, config))


class PartitionCache:
    """TTL cache around discover_partitions.

    Partition topology changes on the scale of cluster maintenance, not page loads --
    caching keeps the submission form off the Slurm controller (NFR-15, NFR-16).
    """

    def __init__(
        self,
        adapter: "SlurmAdapter",
        config: WebConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._adapter = adapter
        self._config = config
        self._clock = clock
        self._cached: Optional[Tuple[float, DiscoveryResult]] = None

    def get(self, force: bool = False) -> DiscoveryResult:
        now = self._clock()
        if not force and self._cached is not None:
            stamped_at, result = self._cached
            if now - stamped_at < self._config.partition_cache_seconds:
                return result
        result = discover_partitions(self._adapter, self._config)
        self._cached = (now, result)
        return result

    def invalidate(self) -> None:
        self._cached = None
