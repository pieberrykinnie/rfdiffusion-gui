"""The ColabDesign / RFdiffusion-fork import bridge.

Every call into ColabDesign or the fork's parse_pdb is routed through this module as a thin
function that imports INSIDE the function body, not at module load. This is the one seam every
other component in this package tests against, instead of each having its own hard import-time
dependency on packages that only exist inside the U1 container. It costs one small module and
changes no documented behaviour; it is what makes rfd-runner importable and its non-GPU logic
testable with zero ColabDesign/torch/JAX installed (see u2b-code-generation-plan.md's "Design
Decision Made Without Asking").

Source modules, verified against reference/diffusion.py lines 79-82 (the notebook's own import
cell) at the pinned ColabDesign commit (e31a56fe1d9b4de25c8697f3a28b75892941cc72, per U1):
    pdb_to_string        -- colabdesign.shared.protein.pdb_to_string
    parse_pdb             -- inference.utils.parse_pdb          (the RFdiffusion FORK, not ColabDesign)
    fix_contigs            -- colabdesign.rf.utils.fix_contigs
    fix_partial_contigs   -- colabdesign.rf.utils.fix_partial_contigs
    fix_pdb                -- colabdesign.rf.utils.fix_pdb
    sym_it                 -- colabdesign.rf.utils.sym_it
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional


def pdb_to_string(pdb: str, chains: Optional[Any] = None) -> str:
    # `chains` is Optional[str] (comma-separated, e.g. request.chains) on the first call and
    # Optional[List[str]] (spec.fixed_chains) on the second -- ColabDesign's own function accepts
    # either, matching reference/diffusion.py's usage at both call sites (lines 272 and 292).
    from colabdesign.shared.protein import pdb_to_string as _pdb_to_string

    return _pdb_to_string(pdb, chains=chains)


def parse_pdb(filename: str) -> Any:
    try:
        Path("/scratch/schedules").mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    from inference.utils import parse_pdb as _parse_pdb

    return _parse_pdb(filename)


def fix_contigs(contigs: List[str], parsed_pdb: Optional[Any]) -> List[str]:
    from colabdesign.rf.utils import fix_contigs as _fix_contigs

    return _fix_contigs(contigs, parsed_pdb)


def fix_partial_contigs(contigs: List[str], parsed_pdb: Optional[Any]) -> List[str]:
    from colabdesign.rf.utils import fix_partial_contigs as _fix_partial_contigs

    return _fix_partial_contigs(contigs, parsed_pdb)


def fix_pdb(pdb_str: str, contigs: List[str]) -> str:
    from colabdesign.rf.utils import fix_pdb as _fix_pdb

    return _fix_pdb(pdb_str, contigs)


def sym_it(x: Any, center: Any, axis1: Any, axis2: Any = None) -> Any:
    from colabdesign.rf.utils import sym_it as _sym_it

    if axis2 is None:
        return _sym_it(x, center, axis1)
    return _sym_it(x, center, axis1, axis2)
