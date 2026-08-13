"""AnAnaS symmetry detection.

Transcribed from reference/diffusion.py's run_ananas() (lines 102-142), invoked via an argument
list (NFR-11) instead of the notebook's shell-string os.system(cmd). See business-logic-model.md
section 5 and business-rules.md sections 1 and 3.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import _colabdesign
from .errors import AnanasUnavailableError, SymmetryDetectionError

RunCmdFn = Callable[[List[str]], None]


@dataclass(frozen=True)
class SymmetryDetection:
    group: str  # "c3", "d2", etc. -- never constructed for "nothing found"
    rmsd: float
    asymmetric_unit_pdb_str: str


class SymmetryDetector:
    def detect_symmetry(
        self,
        pdb_str: str,
        run_dir: Path,
        *,
        ananas_bin: Optional[Path] = None,
        run_cmd: Optional[RunCmdFn] = None,
    ) -> Optional[SymmetryDetection]:
        ananas_bin = ananas_bin if ananas_bin is not None else Path("/opt/weights/bin/ananas")

        # Checked BEFORE any subprocess -- business-rules.md section 3. This is the
        # fail-fast-and-explain path; it must never be reached silently.
        if not (os.path.isfile(ananas_bin) and os.access(ananas_bin, os.X_OK)):
            raise AnanasUnavailableError(str(ananas_bin))

        run_cmd = run_cmd if run_cmd is not None else _default_run_cmd

        run_dir = Path(run_dir)
        pdb_filename = run_dir / "ananas_input.pdb"
        out_filename = run_dir / "ananas.json"
        pdb_filename.write_text(pdb_str)

        run_cmd([str(ananas_bin), str(pdb_filename), "-u", "-j", str(out_filename)])

        try:
            raw = out_filename.read_text()
        except FileNotFoundError:
            # AnAnaS ran but produced no output at all -- treated the same as "found nothing"
            # (matches the notebook's group=None fallback), not a parse error.
            return None

        try:
            out = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SymmetryDetectionError(f"AnAnaS output is not valid JSON: {e}") from e

        if not out:
            # Ran, found nothing (business-rules.md section 1: "not a failure").
            return None

        try:
            results, au = out[0], out[-1]["AU"]
            group = au.get("group")
            if not group:
                return None
            chains = au["chain names"]
            rmsd = results["Average_RMSD"]
        except (KeyError, IndexError, TypeError) as e:
            # A genuine, structurally-malformed result -- distinct from "ran, found nothing"
            # above. Replaces the notebook's bare `except:` (TD-8), which conflated the two.
            raise SymmetryDetectionError(f"unexpected AnAnaS output shape: {e}") from e

        center = results["transforms"][0]["CENTER"]
        axes = [t["AXIS"] for t in results["transforms"]]

        new_lines = []
        for line in pdb_str.split("\n"):
            if line.startswith("ATOM"):
                chain = line[21:22]
                if chain in chains:
                    x = [float(line[i : i + 8]) for i in (30, 38, 46)]
                    if group[0] == "c":
                        x = _colabdesign.sym_it(x, center, axes[0])
                    elif group[0] == "d":
                        x = _colabdesign.sym_it(x, center, axes[1], axes[0])
                    coord_str = "".join("{:8.3f}".format(a) for a in x)
                    new_lines.append(line[:30] + coord_str + line[54:])
            else:
                new_lines.append(line)

        return SymmetryDetection(
            group=group,
            rmsd=rmsd,
            asymmetric_unit_pdb_str="\n".join(new_lines),
        )


def _default_run_cmd(argv: List[str]) -> None:
    subprocess.run(argv, check=True)
