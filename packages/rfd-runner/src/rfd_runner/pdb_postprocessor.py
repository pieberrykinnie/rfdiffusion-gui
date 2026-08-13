"""Post-processes RFdiffusion's raw output PDBs to match the (possibly symmetrised/replicated)
normalised contigs.

Transcribed exactly from reference/diffusion.py lines 345-352, including the trajectory-file
naming RFdiffusion itself imposes.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from . import _colabdesign


class PdbPostProcessor:
    def fix_outputs(self, run_dir: Path, name: str, num_designs: int, contigs: List[str]) -> None:
        run_dir = Path(run_dir)
        for n in range(num_designs):
            paths = [
                run_dir / "traj" / f"{name}_{n}_pX0_traj.pdb",
                run_dir / "traj" / f"{name}_{n}_Xt-1_traj.pdb",
                run_dir / f"{name}_{n}.pdb",
            ]
            for path in paths:
                pdb_str = path.read_text()
                path.write_text(_colabdesign.fix_pdb(pdb_str, contigs))
