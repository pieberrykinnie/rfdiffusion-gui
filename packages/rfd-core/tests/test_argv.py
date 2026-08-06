import pytest

from rfd_core.argv import build_inference_argv, format_hotspot
from rfd_core.iterations import plan_iterations
from rfd_core.modes import DesignMode
from rfd_core.symmetry import SymmetryKind, resolve_symmetry


class TestFormatHotspot:
    def test_none_stays_none(self):
        assert format_hotspot(None) is None

    def test_empty_string_becomes_none(self):
        assert format_hotspot("") is None

    def test_whitespace_only_becomes_none(self):
        assert format_hotspot("   ") is None

    def test_mixed_separators_normalise_to_csv(self):
        # Notebook line 316: ",".join(hotspot.replace(","," ").split())
        assert format_hotspot("E64, E88  E96") == "E64,E88,E96"

    def test_already_csv(self):
        assert format_hotspot("E64,E88,E96") == "E64,E88,E96"


class TestArgvNoShellQuoting:
    """The point of NFR-11: as real argv tokens, no element should ever need
    -- or have -- shell-protective quote characters wrapped around it."""

    def _build(self, **overrides):
        defaults = dict(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["100-100"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
        )
        defaults.update(overrides)
        return build_inference_argv(**defaults)

    def test_no_element_is_wrapped_in_quotes(self):
        argv = self._build(
            symmetry=resolve_symmetry(SymmetryKind.DIHEDRAL, 2, True),
            hotspot="E64,E88",
        )
        for tok in argv:
            assert not tok.startswith("'") and not tok.endswith("'"), tok

    def test_contigmap_value_has_brackets_but_no_surrounding_quotes(self):
        argv = self._build(normalised_contigs=["A163-181", "40-40"])
        contig_arg = next(t for t in argv if t.startswith("contigmap.contigs="))
        assert contig_arg == "contigmap.contigs=[A163-181 40-40]"
        assert "'" not in contig_arg

    def test_hotspot_value_has_brackets_no_quotes(self):
        argv = self._build(hotspot="E64,E88,E96")
        hs_arg = next(t for t in argv if t.startswith("ppi.hotspot_res="))
        assert hs_arg == "ppi.hotspot_res=[E64,E88,E96]"


class TestConfigNameSplitting:
    def test_symmetry_prepends_two_separate_argv_tokens(self):
        argv = build_inference_argv(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.CYCLIC, 3, False),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["100-100"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
        )
        # "--config-name symmetry" must be TWO tokens, not one with an
        # embedded space -- there is no shell to word-split it for Hydra.
        assert argv[0] == "--config-name"
        assert argv[1] == "symmetry"
        assert " " not in argv[0]
        assert " " not in argv[1]


class TestOverrideOrdering:
    def test_free_mode_no_symmetry(self):
        argv = build_inference_argv(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["100-100"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
        )
        assert argv == [
            "inference.output_prefix=outputs/test",
            "inference.num_designs=1",
            "diffuser.T=50",
            "inference.dump_pdb=True",
            "inference.dump_pdb_path=/scratch",
            "contigmap.contigs=[100-100]",
        ]

    def test_fixed_mode_includes_input_pdb(self):
        argv = build_inference_argv(
            mode=DesignMode.FIXED,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.FIXED, 50, "auto"),
            normalised_contigs=["A163-181"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
            input_pdb="outputs/test/input.pdb",
        )
        assert "inference.input_pdb=outputs/test/input.pdb" in argv
        idx_pdb = argv.index("inference.input_pdb=outputs/test/input.pdb")
        idx_T = argv.index("diffuser.T=50")
        assert idx_pdb < idx_T  # input_pdb comes before diffuser.T (notebook order)

    def test_partial_mode_uses_partial_T_key(self):
        argv = build_inference_argv(
            mode=DesignMode.PARTIAL,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.PARTIAL, 200, "auto"),
            normalised_contigs=["A1-10"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
            input_pdb="outputs/test/input.pdb",
        )
        assert "diffuser.partial_T=80" in argv
        assert not any(t.startswith("diffuser.T=") for t in argv)

    def test_full_symmetry_with_guiding_potentials_order(self):
        argv = build_inference_argv(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.DIHEDRAL, 2, True),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["50-50", "50-50", "50-50", "50-50"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
        )
        expected_prefix = [
            "--config-name",
            "symmetry",
            "inference.symmetry=d2",
            'potentials.guiding_potentials=["type:olig_contacts,weight_intra:1,weight_inter:0.1"]',
            "potentials.olig_intra_all=True",
            "potentials.olig_inter_all=True",
            "potentials.guide_scale=2",
            "potentials.guide_decay=quadratic",
        ]
        assert argv[: len(expected_prefix)] == expected_prefix

    def test_beta_model_override_appended(self):
        argv = build_inference_argv(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["100-100"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
            use_beta_model=True,
            beta_ckpt_path="/opt/RFdiffusion/models/Complex_beta_ckpt.pt",
        )
        assert argv[-2] == "inference.ckpt_override_path=/opt/RFdiffusion/models/Complex_beta_ckpt.pt"
        assert argv[-1] == "contigmap.contigs=[100-100]"  # contigs always last

    def test_no_hotspot_element_when_absent(self):
        argv = build_inference_argv(
            mode=DesignMode.FREE,
            symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
            iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
            normalised_contigs=["100-100"],
            output_prefix="outputs/test",
            num_designs=1,
            dump_pdb_path="/scratch",
        )
        assert not any(t.startswith("ppi.hotspot_res") for t in argv)


class TestCallerContractViolations:
    def test_missing_input_pdb_for_fixed_mode_raises(self):
        with pytest.raises(ValueError, match="requires input_pdb"):
            build_inference_argv(
                mode=DesignMode.FIXED,
                symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
                iteration=plan_iterations(DesignMode.FIXED, 50, "auto"),
                normalised_contigs=["A1-10"],
                output_prefix="outputs/test",
                num_designs=1,
                dump_pdb_path="/scratch",
            )

    def test_beta_model_without_ckpt_path_raises(self):
        with pytest.raises(ValueError, match="requires beta_ckpt_path"):
            build_inference_argv(
                mode=DesignMode.FREE,
                symmetry=resolve_symmetry(SymmetryKind.NONE, 1, False),
                iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
                normalised_contigs=["100-100"],
                output_prefix="outputs/test",
                num_designs=1,
                dump_pdb_path="/scratch",
                use_beta_model=True,
            )
