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
        run_dir = self.layout.run_dir(run_id)
        if not run_dir.exists():
            return None
        zips = sorted(run_dir.glob("*.zip"))
        if zips:
            return zips[0]
        return None
        
    def get_structure(self, run_id: str, design_index: int) -> Optional[Path]:
        run_dir = self.layout.run_dir(run_id)
        if not run_dir.exists():
            return None
        
        ignored = {"input.pdb", "ananas_input.pdb"}
        valid_pdbs = [
            p for p in sorted(run_dir.rglob("*.pdb"))
            if not p.name.startswith(".") and p.name not in ignored and p.stat().st_size > 0
        ]
        
        for p in valid_pdbs:
            if p.stem.endswith(f"_{design_index}") or p.stem == f"design_{design_index}":
                return p
        for p in valid_pdbs:
            if "best" in p.stem:
                return p
        frame = run_dir / "current_frame.pdb"
        if frame.exists() and frame.stat().st_size > 0:
            return frame
        if valid_pdbs:
            return valid_pdbs[0]
        return None

    def get_trajectory(self, run_id: str, design_index: int) -> Optional[Path]:
        run_dir = self.layout.run_dir(run_id)
        if not run_dir.exists():
            return None
        trajs = [p for p in sorted(run_dir.rglob("*traj*.pdb")) if p.stat().st_size > 0]
        if trajs:
            return trajs[0]
        return None

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
