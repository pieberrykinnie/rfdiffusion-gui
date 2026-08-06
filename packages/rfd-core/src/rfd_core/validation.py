"""DesignRequest validation (FR-5, FR-4). See business-rules.md for the full
rule table this implements.

Principle (domain-entities.md section 8): errors a user needs to see and act
on are VALUES (ValidationOutcome), not exceptions. Exceptions stay reserved
for states that indicate a bug in the calling code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .contigs import ContigParseError, ContigSpec
from .models import DesignRequest
from .modes import DesignMode, infer_mode
from .symmetry import SymmetryKind

# Q2 (Functional Design): deliberately far below the real chain-letter
# ceiling (26 dihedral / 52 cyclic, from fix_pdb's 52-letter alphabet).
# Nothing scientific is gained above 12-fold symmetry, and staying at 12
# means the chain-letter-exhaustion failure mode can never be reached.
MAX_SYMMETRY_ORDER = 12


@dataclass
class ValidationOutcome:
    ok: bool
    mode: Optional[DesignMode] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def preview_mode(contigs: str) -> Optional[DesignMode]:
    """Best-effort mode preview for the web form (FR-4). Never raises --
    returns None if the contigs string doesn't parse, so a half-typed form
    field just shows nothing rather than an error while the user is typing.
    """
    try:
        return infer_mode(ContigSpec.parse(contigs))
    except ContigParseError:
        return None


def _validate_chain_tokens(chains: str) -> List[str]:
    errors = []
    for tok in chains.replace(",", " ").split():
        if len(tok) != 1 or not tok.isalpha():
            errors.append(f"invalid chain filter token {tok!r}: must be a single letter")
    return errors


def validate(request: DesignRequest) -> ValidationOutcome:
    errors: List[str] = []
    warnings: List[str] = []
    mode: Optional[DesignMode] = None
    spec: Optional[ContigSpec] = None

    if not request.name or "/" in request.name or "\\" in request.name:
        errors.append("name must be non-empty and must not contain path separators")

    try:
        spec = ContigSpec.parse(request.contigs)
        mode = infer_mode(spec)
    except ContigParseError as e:
        errors.append(str(e))

    if mode in (DesignMode.FIXED, DesignMode.PARTIAL) and not request.pdb:
        errors.append(f"mode '{mode.value}' requires a template (pdb)")

    if request.iterations < 1:
        errors.append("iterations must be >= 1")

    if request.num_designs < 1:
        errors.append("num_designs must be >= 1")

    if request.symmetry in (SymmetryKind.CYCLIC, SymmetryKind.DIHEDRAL):
        if not (1 <= request.order <= MAX_SYMMETRY_ORDER):
            errors.append(
                f"order must be between 1 and {MAX_SYMMETRY_ORDER} "
                f"for {request.symmetry.value} symmetry"
            )

    if request.chains:
        errors.extend(_validate_chain_tokens(request.chains))

    if request.partial_T != "auto":
        try:
            pt = int(request.partial_T)
            if pt < 1:
                errors.append("partial_T must be >= 1 when not 'auto'")
        except ValueError:
            errors.append(f"partial_T must be 'auto' or an integer, got {request.partial_T!r}")

    if request.num_seqs < 1:
        errors.append("num_seqs must be >= 1")

    if request.mpnn_sampling_temp < 0:
        errors.append("mpnn_sampling_temp must be > 0")
    elif request.mpnn_sampling_temp == 0:
        warnings.append("mpnn_sampling_temp is 0 -- sampling will be fully deterministic")

    if request.num_recycles < 0:
        errors.append("num_recycles must be >= 0")

    if (
        request.chains
        and spec is not None
        and spec.has_fixed
        and not any(c in spec.fixed_chains for c in request.chains.replace(",", " ").split())
    ):
        warnings.append(
            "'chains' does not include any chain letter referenced by contigs -- check for a typo"
        )

    return ValidationOutcome(ok=len(errors) == 0, mode=mode, errors=errors, warnings=warnings)
