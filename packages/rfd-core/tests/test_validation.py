
from rfd_core.models import DesignRequest
from rfd_core.modes import DesignMode
from rfd_core.validation import MAX_SYMMETRY_ORDER, preview_mode, validate


def make_request(**overrides):
    defaults = dict(
        name="test-run",
        contigs="100",
        partition="gpu",
        walltime="0-08:00:00",
    )
    defaults.update(overrides)
    return DesignRequest(**defaults)


class TestValidRequestPasses:
    def test_minimal_free_design(self):
        outcome = validate(make_request())
        assert outcome.ok
        assert outcome.errors == []
        assert outcome.mode == DesignMode.FREE

    def test_fixed_mode_with_pdb(self):
        outcome = validate(make_request(contigs="A:50", pdb="6MRR"))
        assert outcome.ok
        assert outcome.mode == DesignMode.FIXED

    def test_cyclic_symmetry_within_range(self):
        outcome = validate(make_request(contigs="50", symmetry="cyclic", order=12))
        assert outcome.ok


class TestNameValidation:
    def test_empty_name_rejected(self):
        outcome = validate(make_request(name=""))
        assert not outcome.ok

    def test_path_separator_rejected(self):
        outcome = validate(make_request(name="a/b"))
        assert not outcome.ok
        assert any("path separators" in e for e in outcome.errors)


class TestContigValidation:
    def test_malformed_contigs_becomes_an_error_not_an_exception(self):
        outcome = validate(make_request(contigs="40//40"))
        assert not outcome.ok
        assert any("invalid contig segment" in e for e in outcome.errors)
        assert outcome.mode is None  # could not be determined


class TestTemplateRequiredForFixedAndPartial:
    def test_fixed_mode_without_pdb_rejected(self):
        outcome = validate(make_request(contigs="A:50", pdb=None))
        assert not outcome.ok
        assert any("requires a template" in e for e in outcome.errors)

    def test_partial_mode_without_pdb_rejected(self):
        outcome = validate(make_request(contigs="A1-10", pdb=None))
        assert not outcome.ok

    def test_free_mode_never_needs_pdb(self):
        outcome = validate(make_request(contigs="100", pdb=None))
        assert outcome.ok


class TestNumericFloors:
    def test_iterations_zero_rejected(self):
        outcome = validate(make_request(iterations=0))
        assert not outcome.ok

    def test_iterations_large_value_accepted_no_constraint(self):
        # Q1 = no upper ceiling.
        outcome = validate(make_request(iterations=100_000))
        assert outcome.ok

    def test_num_designs_zero_rejected(self):
        outcome = validate(make_request(num_designs=0))
        assert not outcome.ok

    def test_num_designs_large_value_accepted(self):
        outcome = validate(make_request(num_designs=1000))
        assert outcome.ok

    def test_num_seqs_zero_rejected(self):
        outcome = validate(make_request(num_seqs=0))
        assert not outcome.ok

    def test_num_recycles_zero_is_valid(self):
        # 0 recycles is a real, meaningful AlphaFold setting, not an error.
        outcome = validate(make_request(num_recycles=0))
        assert outcome.ok

    def test_num_recycles_negative_rejected(self):
        outcome = validate(make_request(num_recycles=-1))
        assert not outcome.ok


class TestSymmetryOrderCeiling:
    def test_order_at_ceiling_accepted(self):
        outcome = validate(make_request(contigs="50", symmetry="dihedral", order=MAX_SYMMETRY_ORDER))
        assert outcome.ok

    def test_order_above_ceiling_rejected(self):
        outcome = validate(
            make_request(contigs="50", symmetry="dihedral", order=MAX_SYMMETRY_ORDER + 1)
        )
        assert not outcome.ok
        assert any(str(MAX_SYMMETRY_ORDER) in e for e in outcome.errors)

    def test_order_ignored_when_symmetry_is_none(self):
        # order=99 would be invalid for cyclic/dihedral, but symmetry=none
        # never looks at it.
        outcome = validate(make_request(order=99))
        assert outcome.ok

    def test_order_zero_rejected_for_cyclic(self):
        outcome = validate(make_request(contigs="50", symmetry="cyclic", order=0))
        assert not outcome.ok


class TestPartialTValidation:
    def test_auto_always_valid(self):
        outcome = validate(make_request(partial_T="auto"))
        assert outcome.ok

    def test_numeric_string_valid(self):
        outcome = validate(make_request(contigs="A1-10", pdb="6MRR", partial_T="40"))
        assert outcome.ok

    def test_non_numeric_rejected(self):
        outcome = validate(make_request(partial_T="not-a-number"))
        assert not outcome.ok

    def test_zero_rejected(self):
        outcome = validate(make_request(partial_T="0"))
        assert not outcome.ok


class TestChainsValidation:
    def test_single_letters_valid(self):
        outcome = validate(make_request(contigs="A:50", pdb="6MRR", chains="A,B"))
        assert outcome.ok

    def test_multi_letter_token_rejected(self):
        outcome = validate(make_request(chains="AB"))
        assert not outcome.ok

    def test_chains_not_referenced_in_contigs_is_a_warning_not_an_error(self):
        outcome = validate(make_request(contigs="A:50", pdb="6MRR", chains="Z"))
        assert outcome.ok  # still passes
        assert any("does not include" in w for w in outcome.warnings)


class TestMpnnSamplingTemp:
    def test_positive_valid(self):
        outcome = validate(make_request(mpnn_sampling_temp=0.1))
        assert outcome.ok
        assert outcome.warnings == []

    def test_zero_is_a_warning_not_an_error(self):
        outcome = validate(make_request(mpnn_sampling_temp=0.0))
        assert outcome.ok
        assert any("deterministic" in w for w in outcome.warnings)

    def test_negative_is_an_error(self):
        outcome = validate(make_request(mpnn_sampling_temp=-0.1))
        assert not outcome.ok


class TestPreviewMode:
    def test_valid_contigs_returns_mode(self):
        assert preview_mode("100") == DesignMode.FREE

    def test_invalid_contigs_returns_none_not_raise(self):
        assert preview_mode("40//40") is None

    def test_empty_string_returns_partial(self):
        assert preview_mode("") == DesignMode.PARTIAL
