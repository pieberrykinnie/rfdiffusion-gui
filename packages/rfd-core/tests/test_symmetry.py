import pytest

from rfd_core.symmetry import (
    SymmetryError,
    SymmetryKind,
    apply_detected_group,
    resolve_symmetry,
)


class TestResolveSymmetry:
    def test_none(self):
        plan = resolve_symmetry(SymmetryKind.NONE, order=1, add_potential=False)
        assert plan.group is None and plan.copies == 1 and not plan.deferred

    def test_cyclic(self):
        plan = resolve_symmetry(SymmetryKind.CYCLIC, order=3, add_potential=False)
        assert plan.group == "c3" and plan.copies == 3 and not plan.deferred

    def test_dihedral_copies_is_double_order(self):
        plan = resolve_symmetry(SymmetryKind.DIHEDRAL, order=3, add_potential=False)
        assert plan.group == "d3" and plan.copies == 6

    def test_auto_is_always_deferred(self):
        plan = resolve_symmetry(SymmetryKind.AUTO, order=1, add_potential=False)
        assert plan.deferred is True
        assert plan.group is None and plan.copies == 1

    def test_add_potential_carried_through(self):
        plan = resolve_symmetry(SymmetryKind.CYCLIC, order=2, add_potential=True)
        assert plan.add_potential is True


class TestApplyDetectedGroup:
    def test_cyclic_detection(self):
        plan = resolve_symmetry(SymmetryKind.AUTO, order=1, add_potential=True)
        resolved = apply_detected_group(plan, "c3")
        assert resolved.group == "c3" and resolved.copies == 3 and not resolved.deferred
        assert resolved.add_potential is True  # preserved from the original plan

    def test_dihedral_detection(self):
        plan = resolve_symmetry(SymmetryKind.AUTO, order=1, add_potential=False)
        resolved = apply_detected_group(plan, "d2")
        assert resolved.group == "d2" and resolved.copies == 4

    def test_no_symmetry_detected_disables_symmetry_without_error(self):
        # Matches notebook: prints an error, disables symmetry, run continues.
        plan = resolve_symmetry(SymmetryKind.AUTO, order=1, add_potential=True)
        resolved = apply_detected_group(plan, None)
        assert resolved.group is None and resolved.copies == 1 and not resolved.deferred

    def test_unsupported_group_raises(self):
        plan = resolve_symmetry(SymmetryKind.AUTO, order=1, add_potential=False)
        with pytest.raises(SymmetryError, match="not supported"):
            apply_detected_group(plan, "x5")

    def test_cannot_apply_to_a_non_deferred_plan(self):
        plan = resolve_symmetry(SymmetryKind.CYCLIC, order=3, add_potential=False)
        with pytest.raises(SymmetryError, match="non-deferred"):
            apply_detected_group(plan, "c3")
