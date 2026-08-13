"""Contig normalisation against a real (or absent) parsed template PDB.

Transcribed from the inline logic in reference/diffusion.py's run_diffusion() (lines 271-309,
327). The only contig-path component that imports ColabDesign (via the _colabdesign bridge) --
rfd_core.contigs handles pure grammar only and has no PDB access.
"""
from __future__ import annotations

from typing import Any, List, Optional

from rfd_core import ContigSpec, DesignMode

from . import _colabdesign


class ContigNormaliser:
    def normalise_contigs(
        self,
        spec: ContigSpec,
        mode: DesignMode,
        parsed_pdb: Optional[Any],
        copies: int,
    ) -> List[str]:
        raw_contigs = spec.to_list()

        if mode == DesignMode.PARTIAL:
            normalised = _colabdesign.fix_partial_contigs(raw_contigs, parsed_pdb)
        else:
            # FIXED and FREE both use fix_contigs (notebook lines 306-309, 313); FREE calls it
            # with parsed_pdb=None.
            normalised = _colabdesign.fix_contigs(raw_contigs, parsed_pdb)

        if copies > 1:
            # Notebook line 327: contigs = sum([contigs] * copies, [])
            normalised = normalised * copies

        return normalised
