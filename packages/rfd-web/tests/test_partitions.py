"""C-22: discovered at runtime (FR-6a), annotated rather than filtered (Q3=A)."""
from __future__ import annotations

from rfd_web.config import WebConfig
from rfd_web.slurm.fake import FakeSlurmAdapter
from rfd_web.slurm.partitions import PartitionCache, PartitionInfo, discover_partitions


def _config(**overrides) -> WebConfig:
    env = {"HOME": "/tmp/home"}
    env.update(overrides)
    return WebConfig.from_env(env)


def test_only_gpu_partitions_are_offered(config):
    result = discover_partitions(FakeSlurmAdapter(), config)
    names = [p.name for p in result.partitions]
    assert "skylake" not in names
    assert {"gpu", "agpu", "lgpu"} <= set(names)


def test_duplicate_sinfo_rows_are_collapsed(config):
    duplicated = [
        PartitionInfo(name="gpu", has_gpu=True, max_walltime="7-00:00:00"),
        PartitionInfo(name="gpu", has_gpu=True, max_walltime="7-00:00:00"),
        PartitionInfo(name="agpu", has_gpu=True, max_walltime="3-00:00:00"),
    ]
    result = discover_partitions(FakeSlurmAdapter(partitions_fixture=duplicated), config)
    assert [p.name for p in result.partitions] == ["gpu", "agpu"]


def test_incompatible_partitions_are_annotated_not_removed(config):
    """Q3=A. A filter that silently removes a valid option is the same failure mode as
    the hard-coded list FR-6a forbids -- the image is the user's to replace."""
    result = discover_partitions(FakeSlurmAdapter(), config)
    by_name = {p.name: p for p in result.partitions}
    assert "lgpu" in by_name, "lgpu must still be offered"
    assert by_name["lgpu"].compatible is False
    # The reason names the IMAGE, because that is what the incompatibility is a
    # property of -- not the cluster.
    assert "image" in (by_name["lgpu"].incompatible_reason or "")
    assert by_name["gpu"].compatible is True
    assert by_name["gpu"].incompatible_reason is None


def test_the_incompatible_list_is_configuration_not_code():
    """No partition name is asserted in the codebase; the list comes from the env."""
    config = _config(RFD_INCOMPATIBLE_PARTITIONS="agpu, gpu")
    result = discover_partitions(FakeSlurmAdapter(), config)
    by_name = {p.name: p for p in result.partitions}
    assert by_name["agpu"].compatible is False
    assert by_name["gpu"].compatible is False
    assert by_name["lgpu"].compatible is True


def test_empty_incompatible_list_marks_everything_compatible():
    config = _config(RFD_INCOMPATIBLE_PARTITIONS="")
    result = discover_partitions(FakeSlurmAdapter(), config)
    assert all(p.compatible for p in result.partitions)


def test_unavailable_slurm_degrades_to_empty_plus_warning(config):
    """Discovery failing must never block submission; the caller falls back to a
    free-text partition field pre-filled from RFD_DEFAULT_PARTITION."""
    fake = FakeSlurmAdapter()
    fake.unavailable = True
    result = discover_partitions(fake, config)
    assert result.partitions == []
    assert result.warning and "manually" in result.warning


def test_default_partition_marker_survives_discovery(config):
    result = discover_partitions(FakeSlurmAdapter(), config)
    assert [p.name for p in result.partitions if p.is_default] == ["gpu"]


# -- caching (NFR-15, NFR-16) -------------------------------------------------


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_cache_serves_repeat_reads_without_touching_slurm(config):
    fake = FakeSlurmAdapter()
    clock = _Clock()
    cache = PartitionCache(fake, config, clock=clock)

    calls = {"n": 0}
    original = fake.partitions

    def counting():
        calls["n"] += 1
        return original()

    fake.partitions = counting  # type: ignore[assignment]

    cache.get()
    cache.get()
    assert calls["n"] == 1

    clock.now += config.partition_cache_seconds + 1
    cache.get()
    assert calls["n"] == 2

    cache.invalidate()
    cache.get()
    assert calls["n"] == 3
