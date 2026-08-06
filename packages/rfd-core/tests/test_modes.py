import pytest

from rfd_core.contigs import ContigSpec
from rfd_core.modes import DesignMode, infer_mode


@pytest.mark.parametrize(
    "raw,expected",
    [
        # business-logic-model.md section 2 behaviour table, row for row.
        ("", DesignMode.PARTIAL),
        ("100", DesignMode.FREE),
        ("50:100", DesignMode.FREE),
        ("A:50", DesignMode.FIXED),
        ("40/A163-181/40", DesignMode.FIXED),
        ("A1-10", DesignMode.PARTIAL),
        ("A", DesignMode.PARTIAL),
        # additional notebook-derived cases
        ("E6-155:70-100", DesignMode.FIXED),  # binder: fixed target + free binder length
        ("A3-30/36/A33-68", DesignMode.FIXED),  # loop between fixed segments
    ],
)
def test_mode_inference_matches_notebook(raw, expected):
    assert infer_mode(ContigSpec.parse(raw)) == expected


def test_partial_mode_even_with_multiple_fixed_only_tokens():
    # Multiple chain tokens, all fixed, no free segment anywhere -> still partial.
    spec = ContigSpec.parse("A1-10,B1-10")
    assert infer_mode(spec) == DesignMode.PARTIAL
