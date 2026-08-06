"""Property-based tests (NFR-17). Targeted per the requirements-analysis 11a=B
decision: not a blocking rule set across the codebase, but genuinely warranted
for exactly this logic -- contig parsing / mode inference / iteration
planning / argv assembly is the highest-value code carried over from the
notebook, had zero tests before this unit, and is the shape hypothesis is
good at (arbitrary strings in, an invariant that must always hold out).
"""
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from rfd_core.argv import build_inference_argv
from rfd_core.contigs import ContigSpec
from rfd_core.iterations import IterationError, plan_iterations
from rfd_core.modes import DesignMode, infer_mode
from rfd_core.symmetry import SymmetryKind, resolve_symmetry

settings.register_profile("default", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("default")


# --- Generators for syntactically valid contig strings ----------------------

@st.composite
def free_segment(draw):
    exact = draw(st.booleans())
    if exact:
        return str(draw(st.integers(min_value=1, max_value=999)))
    lo = draw(st.integers(min_value=1, max_value=500))
    hi = draw(st.integers(min_value=lo, max_value=lo + 500))
    return f"{lo}-{hi}"


@st.composite
def fixed_segment(draw):
    chain = draw(st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    shape = draw(st.sampled_from(["whole", "upto", "from", "range", "single"]))
    if shape == "whole":
        return chain
    if shape == "upto":
        return f"{chain}-{draw(st.integers(1, 999))}"
    if shape == "from":
        return f"{chain}{draw(st.integers(1, 999))}-"
    if shape == "single":
        return f"{chain}{draw(st.integers(1, 999))}"
    lo = draw(st.integers(1, 500))
    hi = draw(st.integers(lo, lo + 500))
    return f"{chain}{lo}-{hi}"


@st.composite
def contig_token(draw):
    segs = draw(st.lists(st.one_of(free_segment(), fixed_segment()), min_size=1, max_size=4))
    return "/".join(segs)


@st.composite
def contigs_string(draw):
    tokens = draw(st.lists(contig_token(), min_size=0, max_size=4))
    sep = draw(st.sampled_from([",", ":", " "]))
    return sep.join(tokens)


# --- Properties ---------------------------------------------------------

@given(contigs_string())
def test_generated_strings_always_parse(raw):
    """Sanity check on the generator itself: everything it produces is valid
    input. If this fails, the generator (not rfd_core) has a bug."""
    ContigSpec.parse(raw)


@given(contigs_string())
def test_infer_mode_never_raises_on_valid_contigs(raw):
    spec = ContigSpec.parse(raw)
    mode = infer_mode(spec)
    assert mode in (DesignMode.FREE, DesignMode.FIXED, DesignMode.PARTIAL)


@given(contigs_string())
def test_to_list_round_trip_is_idempotent(raw):
    """Reparsing a spec's own to_list() output yields the same structure."""
    spec1 = ContigSpec.parse(raw)
    rejoined = ",".join(spec1.to_list())
    spec2 = ContigSpec.parse(rejoined)
    assert spec1.to_list() == spec2.to_list()
    assert infer_mode(spec1) == infer_mode(spec2)


@given(
    mode=st.sampled_from(list(DesignMode)),
    iterations=st.integers(min_value=1, max_value=100_000),
    partial_t_raw=st.one_of(
        st.just("auto"),
        st.integers(min_value=-1000, max_value=100_000).map(str),
        st.text(max_size=8),
    ),
)
def test_plan_iterations_never_raises_anything_but_IterationError(mode, iterations, partial_t_raw):
    """The TD-11 fix, stated as an invariant: no input, however malformed,
    produces an unhandled crash. Either a plan comes back, or IterationError
    is raised -- nothing else."""
    try:
        plan = plan_iterations(mode, iterations, partial_t_raw)
    except IterationError:
        return
    assert plan.steps >= 1
    assert plan.hydra_key in ("diffuser.T", "diffuser.partial_T")


@given(
    normalised_contigs=st.lists(
        st.builds(
            lambda a, b: f"{a}-{b}",
            st.integers(1, 500),
            st.integers(1, 500),
        ),
        min_size=1,
        max_size=4,
    ),
    hotspot=st.one_of(st.none(), st.text(alphabet="ABCDEFGHIJ0123456789, ", max_size=20)),
    add_symmetry=st.booleans(),
)
def test_argv_elements_never_carry_notebook_style_quote_wrapping(
    normalised_contigs, hotspot, add_symmetry
):
    """NFR-11, as a property: an argv list built for direct subprocess
    execution must never need -- and must never contain -- the shell-
    protective quote characters the notebook's shell-string version needed."""
    symmetry = resolve_symmetry(
        SymmetryKind.DIHEDRAL if add_symmetry else SymmetryKind.NONE, order=2, add_potential=add_symmetry
    )
    argv = build_inference_argv(
        mode=DesignMode.FREE,
        symmetry=symmetry,
        iteration=plan_iterations(DesignMode.FREE, 50, "auto"),
        normalised_contigs=normalised_contigs,
        output_prefix="outputs/test",
        num_designs=1,
        dump_pdb_path="/scratch",
        hotspot=hotspot,
    )
    for tok in argv:
        assert tok != ""
        assert not tok.startswith("'"), tok
        assert not tok.endswith("'") or "'" not in tok[:-1], tok
