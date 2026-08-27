from __future__ import annotations

from typing import Optional, Any
from pathlib import Path

from rfd_core.paths import PathLayout
from rfd_web.persistence.reader import RunDirectoryReader

class ResultService:
    def __init__(self, layout: PathLayout, reader: RunDirectoryReader):
        self.layout = layout
        self.reader = reader
        
    def get_result_zip(self, run_id: str) -> Optional[Path]:
        return self.get_file(run_id, f"{run_id}_results.zip")
        
    def get_structure(self, run_id: str, design_index: int) -> Optional[Path]:
        path = self.get_file(run_id, f"design_{design_index}.pdb")
        if not path:
            path = self.get_file(run_id, f"designs/design_{design_index}.pdb")
        return path

    def get_trajectory(self, run_id: str, design_index: int) -> Optional[Path]:
        path = self.get_file(run_id, f"trajectory_{design_index}.pdb")
        if not path:
            path = self.get_file(run_id, f"trajectories/trajectory_{design_index}.pdb")
        return path

    def get_best_overlay(self, run_id: str) -> Optional[dict[str, Any]]:
        import json
        metrics_path = self.get_file(run_id, "metrics.json")
        if metrics_path and metrics_path.exists():
            try:
                with open(metrics_path, "r") as f:
                    data = json.load(f)
                    return data.get("best_overlay")
            except Exception:
                return None
        return None

    def get_file(self, run_id: str, relative_path: str) -> Optional[Path]:
        try:
            run_dir = self.layout.run_dir(run_id)
            return self.reader.resolve_within(run_dir, relative_path)
        except (ValueError, FileNotFoundError, RuntimeError):
            return None
