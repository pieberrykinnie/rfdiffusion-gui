import pytest

from rfd_core.contigs import ContigParseError, ContigSpec, get_Ls


class TestTokenisation:
    def test_empty_string_has_no_tokens(self):
        assert ContigSpec.parse("").is_empty

    def test_comma_separates_tokens(self):
        spec = ContigSpec.parse("50,100")
        assert len(spec.tokens) == 2

    def test_colon_separates_tokens(self):
        spec = ContigSpec.parse("50:100")
        assert len(spec.tokens) == 2

    def test_whitespace_separates_tokens(self):
        spec = ContigSpec.parse("50 100")
        assert len(spec.tokens) == 2

    def test_mixed_separators(self):
        spec = ContigSpec.parse("50, 100:  200")
        assert len(spec.tokens) == 3

    def test_slash_separates_segments_within_one_token(self):
        spec = ContigSpec.parse("40/A163-181/40")
        assert len(spec.tokens) == 1
        assert len(spec.tokens[0]) == 3


class TestSegmentClassification:
    @pytest.mark.parametrize(
        "raw,chain",
        [
            ("A163-181", "A"),
            ("A-181", "A"),
            ("A33-", "A"),
            ("A", "A"),
            ("A163", "A"),
            ("Z1-2", "Z"),
        ],
    )
    def test_fixed_segments(self, raw, chain):
        spec = ContigSpec.parse(raw)
        seg = spec.tokens[0][0]
        assert seg.is_fixed is True
        assert seg.chain == chain

    @pytest.mark.parametrize("raw", ["40", "50-100", "1", "999"])
    def test_free_segments(self, raw):
        spec = ContigSpec.parse(raw)
        seg = spec.tokens[0][0]
        assert seg.is_fixed is False
        assert seg.chain is None

    def test_free_exact_length(self):
        seg = ContigSpec.parse("40").tokens[0][0]
        assert seg.length_min == 40
        assert seg.length_max == 40

    def test_free_range(self):
        seg = ContigSpec.parse("70-100").tokens[0][0]
        assert seg.length_min == 70
        assert seg.length_max == 100


class TestMalformedSegments:
    def test_empty_segment_between_slashes(self):
        with pytest.raises(ContigParseError):
            ContigSpec.parse("40//40")

    def test_segment_starting_with_dash(self):
        with pytest.raises(ContigParseError):
            ContigSpec.parse("-40")

    def test_bare_zero_rejected(self):
        # Deliberate deviation from the notebook: ColabDesign silently drops
        # a bare "0" segment. We reject it instead.
        with pytest.raises(ContigParseError, match="length-0"):
            ContigSpec.parse("0")

    def test_zero_lower_bound_range_rejected(self):
        with pytest.raises(ContigParseError, match="length-0"):
            ContigSpec.parse("0-10")

    def test_range_upper_less_than_lower_rejected(self):
        with pytest.raises(ContigParseError):
            ContigSpec.parse("100-50")

    def test_malformed_range_extra_dash(self):
        with pytest.raises(ContigParseError):
            ContigSpec.parse("10-20-30")

    def test_segment_neither_chain_reference_nor_numeric(self):
        # Leading character is neither alphabetic nor numeric (e.g. a typo'd
        # symbol) -- must be rejected with a clear reason, not silently
        # misclassified as free or fixed.
        with pytest.raises(ContigParseError, match="neither a chain reference"):
            ContigSpec.parse("#40")


class TestFixedChains:
    def test_deduplicates_and_preserves_first_appearance_order(self):
        spec = ContigSpec.parse("A1-10/B1-10/A20-30")
        assert spec.fixed_chains == ["A", "B"]

    def test_empty_when_no_fixed_segments(self):
        assert ContigSpec.parse("100").fixed_chains == []


class TestHasFreeHasFixed:
    def test_pure_free(self):
        spec = ContigSpec.parse("100")
        assert spec.has_free and not spec.has_fixed

    def test_pure_fixed(self):
        spec = ContigSpec.parse("A1-10")
        assert spec.has_fixed and not spec.has_free

    def test_mixed(self):
        spec = ContigSpec.parse("40/A163-181/40")
        assert spec.has_free and spec.has_fixed


class TestToList:
    def test_round_trips_token_structure(self):
        spec = ContigSpec.parse("40/A163-181/40,50")
        assert spec.to_list() == ["40/A163-181/40", "50"]


class TestNotebookInstructionExamples:
    """Every contig example from reference/diffusion.py's own instructions
    block (lines 568-596), parse-only (full range resolution needs a parsed
    PDB and is U2b's job -- this only proves the grammar accepts them)."""

    @pytest.mark.parametrize(
        "raw",
        [
            "100",  # unconditional monomer
            "50:100",  # hetero-oligomer
            "A:50",  # binder design
            "E6-155:70-100",  # binder with a length range
            "40/A163-181/40",  # motif scaffolding
            "A3-30/36/A33-68",  # loop between two fixed segments
            "A1-10",  # partial diffusion, first 10 fixed
            "A",  # partial diffusion, fix whole chain A
        ],
    )
    def test_parses_without_error(self, raw):
        ContigSpec.parse(raw)  # must not raise


class TestGetLs:
    def test_single_fixed_range(self):
        # A163-181 inclusive is 181-163+1 = 19 residues
        assert get_Ls(["A163-181"]) == [19]

    def test_single_free_exact(self):
        assert get_Ls(["40-40"]) == [40]

    def test_mixed_chain_sums_subsegments(self):
        # 40 free + 19 fixed (A163-181) + 40 free = 99
        assert get_Ls(["40-40/A163-181/40-40"]) == [99]

    def test_multiple_chains(self):
        assert get_Ls(["50-50", "100-100"]) == [50, 100]
