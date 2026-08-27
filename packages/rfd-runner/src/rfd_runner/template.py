"""Template PDB resolution.

Transcribed from reference/diffusion.py's get_pdb() (lines 85-100), with the Colab upload branch
removed -- replaced by a pre-uploaded file already living in run_dir (staged by U3/U4 before the
job was submitted), which the local-path branch below picks up unchanged. See
business-logic-model.md section 5.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional

FetchFn = Callable[[List[str]], None]


class TemplateResolver:
    def resolve_template(
        self,
        pdb: Optional[str],
        run_dir: Path,
        *,
        fetch: Optional[FetchFn] = None,
    ) -> Optional[Path]:
        if not pdb:
            return None

        fetch = fetch if fetch is not None else _default_fetch
        run_dir = Path(run_dir)

        local = Path(pdb)
        if local.is_file():
            return local
        if (run_dir / pdb).is_file():
            return run_dir / pdb

        if len(pdb) == 4:
            pdb1 = run_dir / f"{pdb}.pdb1"
            if not pdb1.is_file():
                gz = run_dir / f"{pdb}.pdb1.gz"
                fetch(["wget", "-q", "-O", str(gz), f"https://files.rcsb.org/download/{pdb}.pdb1.gz"])
                fetch(["gunzip", "-f", str(gz)])
            return pdb1

        dest = run_dir / f"AF-{pdb}-F1-model_v3.pdb"
        if not dest.is_file():
            fetch(
                [
                    "wget",
                    "-q",
                    "-O",
                    str(dest),
                    f"https://alphafold.ebi.ac.uk/files/AF-{pdb}-F1-model_v3.pdb",
                ]
            )
        return dest


def _default_fetch(argv: List[str]) -> None:
    subprocess.run(argv, check=True)
