"""Diffusion step-count planning.

Transcribed from reference/diffusion.py lines 300-309. See
business-logic-model.md section 4.
"""
from __future__ import annotations

from dataclasses import dataclass

from .modes import DesignMode


class IterationError(ValueError):
    """Raised for a partial_T that cannot yield a usable step count.

    Fixes TD-11: the notebook let `int(partial_T)` raise an unhandled
    ValueError deep inside run_diffusion. Here it is validated up front, with
    a message a web form can show directly.
    """


@dataclass(frozen=True)
class IterationPlan:
    steps: int
    hydra_key: str  # "diffuser.T" | "diffuser.partial_T"


def plan_iterations(mode: DesignMode, iterations: int, partial_T: str) -> IterationPlan:
    if mode == DesignMode.PARTIAL:
        if partial_T == "auto":
            # Notebook line 302: int(80 * (iterations / 200))
            steps = int(80 * (iterations / 200))
        else:
            try:
                steps = int(partial_T)
            except (TypeError, ValueError):
                raise IterationError(
                    f"partial_T must be 'auto' or an integer, got {partial_T!r}"
                )
        if steps < 1:
            raise IterationError(
                f"computed partial_T is {steps}, which is not usable "
                "(try a larger iterations value or an explicit partial_T)"
            )
        return IterationPlan(steps=steps, hydra_key="diffuser.partial_T")

    return IterationPlan(steps=iterations, hydra_key="diffuser.T")
