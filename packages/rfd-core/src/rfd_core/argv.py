"""RFdiffusion inference argument-list assembly.

Transcribed from reference/diffusion.py lines 234-332, but built as a `list`
of argv tokens for subprocess execution with NO shell (NFR-11), fixing TD-7.

Two things change shape (not behaviour) versus the notebook, both documented
in business-logic-model.md section 5:

1. No quote characters are added around values like "[...]". The notebook
   needed them to protect the value from the SHELL when it built one long
   command string. Passed as a real argv list, there is no shell in between
   to strip them -- adding quote characters here would make them literally
   part of the value Hydra parses, which is wrong.

2. "--config-name symmetry" was one opts-list element containing an internal
   space (harmless when later joined into a shell string). As two real argv
   tokens it MUST be split into ["--config-name", "symmetry"] -- Hydra's CLI
   parses --flag and its value as separate tokens at the exec level, and
   without a shell there is no word-splitting to separate them for it.
"""
from __future__ import annotations

from typing import List, Optional

from .iterations import IterationPlan
from .modes import DesignMode
from .symmetry import SymmetryPlan


def format_hotspot(hotspot: Optional[str]) -> Optional[str]:
    """Normalise mixed comma/space-separated residues to a CSV string.

    Notebook line 316: ",".join(hotspot.replace(","," ").split())
    Returns None for absent or whitespace-only input (matches the
    `hotspot != ""` guard at line 315).
    """
    if hotspot is None:
        return None
    csv = ",".join(hotspot.replace(",", " ").split())
    return csv if csv else None


def build_inference_argv(
    *,
    mode: DesignMode,
    symmetry: SymmetryPlan,
    iteration: IterationPlan,
    normalised_contigs: List[str],
    output_prefix: str,
    num_designs: int,
    dump_pdb_path: str,
    input_pdb: Optional[str] = None,
    hotspot: Optional[str] = None,
    use_beta_model: bool = False,
    beta_ckpt_path: Optional[str] = None,
) -> List[str]:
    """Build the RFdiffusion run_inference.py argument list.

    `normalised_contigs` and `input_pdb` are supplied by the caller (U2b's
    ContigNormaliser/TemplateResolver) -- this function is pure and has no
    filesystem or PDB access of its own.

    Raises ValueError for caller-contract violations (missing input_pdb for a
    mode that requires one, missing beta_ckpt_path when use_beta_model is
    set) -- these indicate a bug in the caller, not bad user input, which by
    this point has already been rejected via ValidationOutcome.
    """
    argv: List[str] = []

    # Symmetry config is prepended (notebook line 326: sym_opts + opts).
    if symmetry.group is not None:
        argv.append("--config-name")
        argv.append("symmetry")
        argv.append(f"inference.symmetry={symmetry.group}")
        if symmetry.add_potential:
            argv.append(
                'potentials.guiding_potentials=["type:olig_contacts,weight_intra:1,weight_inter:0.1"]'
            )
            argv.append("potentials.olig_intra_all=True")
            argv.append("potentials.olig_inter_all=True")
            argv.append("potentials.guide_scale=2")
            argv.append("potentials.guide_decay=quadratic")

    argv.append(f"inference.output_prefix={output_prefix}")
    argv.append(f"inference.num_designs={num_designs}")

    if mode in (DesignMode.FIXED, DesignMode.PARTIAL):
        if input_pdb is None:
            raise ValueError(f"mode={mode.value} requires input_pdb")
        argv.append(f"inference.input_pdb={input_pdb}")

    argv.append(f"{iteration.hydra_key}={iteration.steps}")

    hs = format_hotspot(hotspot)
    if hs:
        argv.append(f"ppi.hotspot_res=[{hs}]")

    argv.append("inference.dump_pdb=True")
    argv.append(f"inference.dump_pdb_path={dump_pdb_path}")

    if use_beta_model:
        if beta_ckpt_path is None:
            raise ValueError("use_beta_model=True requires beta_ckpt_path")
        argv.append(f"inference.ckpt_override_path={beta_ckpt_path}")

    argv.append(f"contigmap.contigs=[{' '.join(normalised_contigs)}]")

    return argv
