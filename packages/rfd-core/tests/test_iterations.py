import pytest

from rfd_core.iterations import IterationError, plan_iterations
from rfd_core.modes import DesignMode


class TestNonPartialModes:
    def test_free_mode_uses_diffuser_T(self):
        plan = plan_iterations(DesignMode.FREE, 50, "auto")
        assert plan.steps == 50 and plan.hydra_key == "diffuser.T"

    def test_fixed_mode_uses_diffuser_T(self):
        plan = plan_iterations(DesignMode.FIXED, 100, "auto")
        assert plan.steps == 100 and plan.hydra_key == "diffuser.T"

    def test_partial_T_ignored_outside_partial_mode(self):
        # Non-partial modes never look at partial_T at all.
        plan = plan_iterations(DesignMode.FREE, 50, "not-a-number")
        assert plan.steps == 50


class TestPartialModeAuto:
    def test_notebook_default_200_yields_80(self):
        # Notebook's own worked example: int(80 * (200/200)) = 80.
        plan = plan_iterations(DesignMode.PARTIAL, 200, "auto")
        assert plan.steps == 80 and plan.hydra_key == "diffuser.partial_T"

    def test_ui_default_50_yields_20(self):
        plan = plan_iterations(DesignMode.PARTIAL, 50, "auto")
        assert plan.steps == 20

    @pytest.mark.parametrize("iterations,expected", [(200, 80), (100, 40), (25, 10), (10, 4)])
    def test_formula(self, iterations, expected):
        assert plan_iterations(DesignMode.PARTIAL, iterations, "auto").steps == expected

    def test_too_small_iterations_raises_rather_than_silently_producing_zero_steps(self):
        # int(80 * (1/200)) == 0 -- not usable, and the notebook never guarded it.
        with pytest.raises(IterationError, match="not usable"):
            plan_iterations(DesignMode.PARTIAL, 1, "auto")


class TestPartialModeExplicit:
    def test_explicit_numeric_string(self):
        plan = plan_iterations(DesignMode.PARTIAL, 200, "40")
        assert plan.steps == 40

    def test_non_numeric_raises_iteration_error_not_bare_value_error(self):
        # Fixes TD-11: notebook let int(partial_T) crash unhandled.
        with pytest.raises(IterationError, match="'auto' or an integer"):
            plan_iterations(DesignMode.PARTIAL, 200, "not-a-number")

    def test_zero_raises(self):
        with pytest.raises(IterationError):
            plan_iterations(DesignMode.PARTIAL, 200, "0")

    def test_negative_raises(self):
        with pytest.raises(IterationError):
            plan_iterations(DesignMode.PARTIAL, 200, "-5")
