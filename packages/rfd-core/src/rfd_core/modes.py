"""Design-mode inference: the highest-value logic carried over from the notebook.

Transcribed from reference/diffusion.py lines 252-268. See
business-logic-model.md section 2 for the full behaviour table.
"""
from __future__ import annotations

from enum import Enum

from .contigs import ContigSpec


class DesignMode(str, Enum):
    FREE = "free"
    FIXED = "fixed"
    PARTIAL = "partial"


def infer_mode(spec: ContigSpec) -> DesignMode:
    """Derive the RFdiffusion protocol from a parsed contig spec.

    Rule (notebook lines 263-268):
        no chain tokens, or no free segment anywhere -> PARTIAL
        otherwise, any fixed segment present         -> FIXED
        otherwise (free segments only)                -> FREE
    """
    if spec.is_empty or not spec.has_free:
        return DesignMode.PARTIAL
    if spec.has_fixed:
        return DesignMode.FIXED
    return DesignMode.FREE
