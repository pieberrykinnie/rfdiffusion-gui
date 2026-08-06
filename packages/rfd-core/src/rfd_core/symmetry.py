"""Symmetry resolution.

Transcribed from reference/diffusion.py lines 240-248, 280-289, 319-327. See
business-logic-model.md section 3.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SymmetryKind(str, Enum):
    NONE = "none"
    AUTO = "auto"
    CYCLIC = "cyclic"
    DIHEDRAL = "dihedral"


class SymmetryError(ValueError):
    """Raised on a programmer error (wrong call sequence) or an unsupported
    detected group. Not raised for 'no symmetry detected' -- that is an
    expected AnAnaS outcome, matching the notebook's behaviour of disabling
    symmetry and continuing.
    """


@dataclass(frozen=True)
class SymmetryPlan:
    group: Optional[str]
    copies: int
    deferred: bool
    add_potential: bool


def resolve_symmetry(kind: SymmetryKind, order: int, add_potential: bool) -> SymmetryPlan:
    """Resolve a symmetry kind/order into a plan.

    AUTO is always deferred=True: resolution requires running AnAnaS against
    the actual template, which needs a parsed PDB and therefore happens in
    rfd-runner (U2b). apply_detected_group() below specifies the rule both
    sides must implement identically once AnAnaS has run.
    """
    if kind == SymmetryKind.NONE:
        return SymmetryPlan(group=None, copies=1, deferred=False, add_potential=add_potential)
    if kind == SymmetryKind.CYCLIC:
        return SymmetryPlan(group=f"c{order}", copies=order, deferred=False, add_potential=add_potential)
    if kind == SymmetryKind.DIHEDRAL:
        return SymmetryPlan(group=f"d{order}", copies=2 * order, deferred=False, add_potential=add_potential)
    if kind == SymmetryKind.AUTO:
        return SymmetryPlan(group=None, copies=1, deferred=True, add_potential=add_potential)
    raise SymmetryError(f"unknown symmetry kind: {kind!r}")  # pragma: no cover - exhaustive enum


def apply_detected_group(plan: SymmetryPlan, detected: Optional[str]) -> SymmetryPlan:
    """Fold an AnAnaS detection result into a deferred plan.

    detected is None when AnAnaS found nothing (notebook: prints an error,
    disables symmetry, run continues unsymmetric) -- NOT an error here either;
    it is a legitimate outcome the caller must handle the same way.

    Raises SymmetryError for a detected group RFdiffusion doesn't support
    (anything not c* or d*) or if called on a plan that wasn't deferred.
    """
    if not plan.deferred:
        raise SymmetryError("apply_detected_group() called on a non-deferred plan")

    if detected is None:
        return SymmetryPlan(group=None, copies=1, deferred=False, add_potential=plan.add_potential)

    kind_char = detected[0] if detected else ""
    if kind_char == "c":
        return SymmetryPlan(group=detected, copies=int(detected[1:]), deferred=False, add_potential=plan.add_potential)
    if kind_char == "d":
        return SymmetryPlan(group=detected, copies=2 * int(detected[1:]), deferred=False, add_potential=plan.add_potential)
    raise SymmetryError(f"detected symmetry group {detected!r} is not supported (only c* and d* groups)")
