"""Result staging (checked, not performed) and packaging.

G-13 ("stage out before job end") is satisfied BY CONSTRUCTION, not by a copy step
(business-logic-model.md section 1.3): output_prefix already points directly at the persistent,
bind-mounted run directory, so final outputs are written to persistent storage from the moment
they exist. stage_out() exists to make that invariant checkable rather than assumed.

package_results() is an improvement over the notebook's `!zip -r` shell-out (line 565): same file
selection, zero subprocess, NFR-11 by construction rather than by argument-list discipline.
"""
from __future__ import annotations

import zipfile
from pathlib import Path


class ResultPackager:
    def stage_out(self, tmpdir: Path, run_dir: Path) -> None:
        tmpdir = Path(tmpdir)
        run_dir = Path(run_dir)
        leaked = sorted(p for p in tmpdir.glob("*.pdb") if p.is_file())
        if leaked:
            raise AssertionError(
                f"G-13 violated: found final-looking output(s) {leaked} still in ephemeral "
                f"scratch {tmpdir} instead of persistent {run_dir} -- inference.output_prefix "
                f"should already point directly at run_dir, so nothing should ever need staging out"
            )

    def package_results(self, run_dir: Path, name: str) -> Path:
        run_dir = Path(run_dir)
        zip_path = run_dir / f"{name}.result.zip"

        top_level = sorted(p for p in run_dir.glob(f"{name}*") if p.is_file() and p != zip_path)
        traj_dir = run_dir / "traj"
        traj_files = (
            sorted(p for p in traj_dir.glob(f"{name}*") if p.is_file()) if traj_dir.is_dir() else []
        )

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in top_level:
                zf.write(p, arcname=p.name)
            for p in traj_files:
                zf.write(p, arcname=f"traj/{p.name}")

        return zip_path
