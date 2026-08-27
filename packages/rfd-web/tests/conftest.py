"""Shared fixtures.

Everything here is real: real SQLite files, real directories, real bash. The only thing
faked is Slurm itself, which is the seam NFR-18 exists for.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from rfd_core import DesignRequest, PathLayout, RunRecord, StageState

from rfd_web.config import WebConfig
from rfd_web.persistence.repository import RunRepository
from rfd_web.slurm.fake import FakeSlurmAdapter


@pytest.fixture
def layout(tmp_path: Path) -> PathLayout:
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "bin").mkdir()
    image = tmp_path / "images" / "rfdiffusion.sif"
    image.parent.mkdir(parents=True)
    image.write_text("not really a sif")
    outputs = tmp_path / "runs"
    outputs.mkdir()
    return PathLayout(
        weights_root=weights,
        image_path=image,
        output_root=outputs,
        database_path=tmp_path / "db" / "runs.sqlite",
    )


@pytest.fixture
def config(tmp_path: Path) -> WebConfig:
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    return WebConfig.from_env(
        {
            "HOME": str(tmp_path),
            "RFD_PROJECT_ROOT": str(project),
            "APPTAINER_CACHEDIR": str(cache),
            "RFD_DEFAULT_ACCOUNT": "def-cardona",
        }
    )


@pytest.fixture
def repository(layout: PathLayout) -> RunRepository:
    return RunRepository(layout.database_path)


@pytest.fixture
def adapter() -> FakeSlurmAdapter:
    return FakeSlurmAdapter()


def make_request(**overrides) -> DesignRequest:
    params = dict(
        name="smoke",
        contigs="80",
        partition="gpu",
        walltime="0-00:30:00",
        iterations=50,
        num_designs=1,
    )
    params.update(overrides)
    return DesignRequest(**params)


def make_record(run_dir: Path, run_id: str = "smoke", **overrides) -> RunRecord:
    request = overrides.pop("request", None) or make_request()
    record = RunRecord(
        run_id=run_id,
        name=overrides.pop("name", run_id),
        run_dir=str(run_dir),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        request=request,
        backbone_state=overrides.pop("backbone_state", StageState.PENDING),
        validate_state=overrides.pop("validate_state", StageState.PENDING),
        **overrides,
    )
    return record


@pytest.fixture
def written_record(layout: PathLayout):
    """A run directory with a saved run.json, ready to be read back."""

    def _make(run_id: str = "smoke", **overrides) -> RunRecord:
        run_dir = layout.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        record = make_record(run_dir, run_id=run_id, **overrides)
        record.save(run_dir)
        return record

    return _make


# -- stub Slurm binaries, for exercising CliSlurmAdapter for real -----------------


def write_stub(bin_dir: Path, name: str, body: str) -> Path:
    """Drop an executable shell stub named `name` into `bin_dir`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def stub_bin(tmp_path: Path, monkeypatch):
    """A directory prepended to PATH, for stub slurm/container binaries."""
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", "{0}{1}{2}".format(bin_dir, os.pathsep, os.environ["PATH"]))
    return bin_dir

from fastapi.testclient import TestClient
from httpx import AsyncClient
from rfd_web.app import create_app
import pytest_asyncio

@pytest.fixture
def app(config, adapter, layout):
    return create_app(config=config, slurm=adapter, layout=layout)

from httpx import ASGITransport

@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
def sync_client(app):
    return TestClient(app)
