from rfd_core import ContigSpec, DesignMode

from rfd_runner import _colabdesign
from rfd_runner.contig_normaliser import ContigNormaliser


def test_fixed_mode_routes_to_fix_contigs(monkeypatch):
    calls = []

    def fake_fix_contigs(contigs, parsed_pdb):
        calls.append(("fix_contigs", contigs, parsed_pdb))
        return ["A1-10/20-20"]

    def fake_fix_partial_contigs(contigs, parsed_pdb):
        calls.append(("fix_partial_contigs", contigs, parsed_pdb))
        return ["should-not-be-called"]

    monkeypatch.setattr(_colabdesign, "fix_contigs", fake_fix_contigs)
    monkeypatch.setattr(_colabdesign, "fix_partial_contigs", fake_fix_partial_contigs)

    spec = ContigSpec.parse("A1-10/20")
    result = ContigNormaliser().normalise_contigs(spec, DesignMode.FIXED, parsed_pdb="PDB", copies=1)

    assert result == ["A1-10/20-20"]
    assert len(calls) == 1
    assert calls[0][0] == "fix_contigs"
    assert calls[0][2] == "PDB"


def test_free_mode_routes_to_fix_contigs_with_none_pdb(monkeypatch):
    calls = []
    monkeypatch.setattr(_colabdesign, "fix_contigs", lambda c, p: calls.append((c, p)) or ["40-40"])

    spec = ContigSpec.parse("40")
    result = ContigNormaliser().normalise_contigs(spec, DesignMode.FREE, parsed_pdb=None, copies=1)

    assert result == ["40-40"]
    assert calls[0][1] is None


def test_partial_mode_routes_to_fix_partial_contigs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        _colabdesign, "fix_partial_contigs", lambda c, p: calls.append((c, p)) or ["A1-10"]
    )

    spec = ContigSpec.parse("A1-10")
    result = ContigNormaliser().normalise_contigs(
        spec, DesignMode.PARTIAL, parsed_pdb="PDB", copies=1
    )

    assert result == ["A1-10"]
    assert len(calls) == 1


def test_copies_greater_than_one_replicates_exactly(monkeypatch):
    monkeypatch.setattr(_colabdesign, "fix_contigs", lambda c, p: ["40-40", "50-50"])

    spec = ContigSpec.parse("40 50")
    result = ContigNormaliser().normalise_contigs(spec, DesignMode.FREE, parsed_pdb=None, copies=3)

    # sum([contigs] * copies, []) -- notebook line 327
    assert result == ["40-40", "50-50"] * 3
