"""Crash-safe small-file JSON persistence for run.json and progress.json.

Both files may be written on a GPU compute node and read from a login node
over NFS (U1 deployment-architecture.md). Writing via a same-directory temp
file plus os.replace keeps that atomic even across NFS: a reader never
observes a partially-written file.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def write_json_atomic(path: Path, model: BaseModel) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = model.model_dump_json(indent=2)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: Path, model_cls: Type[T]) -> Optional[T]:
    """Returns None for a missing, empty, or unparseable file.

    Callers decide whether that absence is meaningful (RunRecord.load raises
    FileNotFoundError itself when this returns None) or expected
    (ProgressState.load, before the first update).
    """
    path = Path(path)
    try:
        raw = path.read_text()
    except (FileNotFoundError, OSError):
        return None
    if not raw.strip():
        return None
    try:
        return model_cls.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError):
        return None
