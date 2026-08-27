"""WebConfig.from_env -- defaults, and not falling over on a typo."""
from __future__ import annotations

from pathlib import Path

from rfd_web.config import WebConfig


def test_defaults_match_env_example():
    config = WebConfig.from_env({"HOME": "/home/someone"})
    assert config.status_poll_seconds == 5
    assert config.slurm_timeout_seconds == 30
    assert config.partition_cache_seconds == 300
    assert config.progress_stale_seconds == 120
    assert config.log_tail_lines == 50
    assert config.incompatible_partitions == ("lgpu",)
    assert config.default_partition == "gpu"
    assert config.default_gpus == 1
    assert config.default_cpus_per_task == 6
    assert config.default_mem_per_cpu == "6000M"
    assert config.default_walltime == "0-08:00:00"
    assert config.project_root == Path("/home/someone/rfdiffusion-gui")
    assert config.apptainer_cachedir == Path("/home/someone/.cache/apptainer")


def test_a_typo_in_a_numeric_variable_falls_back_rather_than_crashing():
    """This runs at import time on a login node; the default is always safe, and a
    wrong value is not worth taking the app down for."""
    config = WebConfig.from_env({"HOME": "/h", "RFD_STATUS_POLL_SECONDS": "five"})
    assert config.status_poll_seconds == 5


def test_an_empty_numeric_variable_uses_the_default():
    assert WebConfig.from_env({"HOME": "/h", "RFD_LOG_TAIL_LINES": "  "}).log_tail_lines == 50


def test_an_unset_account_is_none_so_the_directive_is_omitted():
    """env.example documents "leave unset to omit --account entirely"; None keeps that
    distinct from an account literally named ""."""
    assert WebConfig.from_env({"HOME": "/h"}).default_account is None
    assert WebConfig.from_env({"HOME": "/h", "RFD_DEFAULT_ACCOUNT": "  "}).default_account is None
    assert WebConfig.from_env({"HOME": "/h", "RFD_DEFAULT_ACCOUNT": "def-x"}).default_account == "def-x"


def test_incompatible_partitions_tolerates_spacing_and_trailing_commas():
    config = WebConfig.from_env({"HOME": "/h", "RFD_INCOMPATIBLE_PARTITIONS": " lgpu , agpu ,"})
    assert config.incompatible_partitions == ("lgpu", "agpu")
    assert config.is_compatible("gpu") is True
    assert config.is_compatible("agpu") is False
