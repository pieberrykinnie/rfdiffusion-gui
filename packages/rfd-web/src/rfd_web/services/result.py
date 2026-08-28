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
        if not trajs:
            return None
        for p in trajs:
            if f"_{design_index}_pX0" in p.name:
                return p
        for p in trajs:
            if f"_{design_index}_" in p.name or f"trajectory_{design_index}" in p.name or f"traj_{design_index}" in p.name or f"_{design_index}." in p.name:
                return p
        return trajs[0]

    def get_best_overlay(self, run_id: str) -> Optional[dict[str, Any]]:
        run_dir = self.layout.run_dir(run_id)
        if not run_dir.exists():
            return None

        # 1. Check if metrics.json explicitly provides best_overlay
        metrics_path = self.get_file(run_id, "metrics.json")
        if metrics_path and metrics_path.exists():
            try:
                import json
                with open(metrics_path, "r") as f:
                    data = json.load(f)
                    if "best_overlay" in data:
                        return data["best_overlay"]
            except Exception:
                pass

        # 2. Determine best design index and RMSD from best.pdb
        best_idx = self.reader.best_design_index(run_dir)
        if best_idx is None:
            best_idx = 0

        rmsd: Optional[float] = None
        best_pdb_candidates = [run_dir / "best.pdb"] + list(run_dir.glob("*/best.pdb"))
        for bp in best_pdb_candidates:
            if bp.is_file():
                try:
                    with bp.open("r") as f:
                        for line in f:
                            if "RMSD" in line:
                                import re
                                m = re.search(r"RMSD\s+([\d\.]+)", line)
                                if m:
                                    rmsd = float(m.group(1))
                                    break
                except Exception:
                    pass

        # 3. Find design backbone PDB
        design_pdb_path = self.get_structure(run_id, best_idx)

        # 4. Find AlphaFold validation PDB
        af_candidates = [
            run_dir / f"best_design{best_idx}.pdb",
            run_dir / "best_design.pdb",
            run_dir / "best.pdb",
        ] + list(run_dir.glob("*/best_design*.pdb")) + list(run_dir.glob("*/best.pdb"))

        af_pdb_path: Optional[Path] = None
        for p in af_candidates:
            if p.is_file() and p.stat().st_size > 0:
                af_pdb_path = p
                break

        if design_pdb_path and af_pdb_path and design_pdb_path.exists() and af_pdb_path.exists():
            try:
                design_pdb_text = design_pdb_path.read_text()
                af_pdb_text = af_pdb_path.read_text()
                if "ATOM" in design_pdb_text or "ATOM" in af_pdb_text:
                    return {
                        "design_index": best_idx,
                        "rmsd": rmsd,
                        "design_pdb": design_pdb_text,
                        "af_pdb": af_pdb_text,
                    }
            except Exception:
                return None

        return None

    def get_file(self, run_id: str, relative_path: str) -> Optional[Path]:
        try:
            run_dir = self.layout.run_dir(run_id)
            return self.reader.resolve_within(run_dir, relative_path)
        except (ValueError, FileNotFoundError, RuntimeError):
            return None
