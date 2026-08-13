from rfd_runner import _colabdesign
from rfd_runner.pdb_postprocessor import PdbPostProcessor


def test_fixes_all_three_paths_per_design(tmp_path, monkeypatch):
    (tmp_path / "traj").mkdir()
    contigs = ["A1-10/20-20"]
    calls = []

    def fake_fix_pdb(pdb_str, contigs_arg):
        calls.append((pdb_str, contigs_arg))
        return pdb_str.upper()

    monkeypatch.setattr(_colabdesign, "fix_pdb", fake_fix_pdb)

    for n in range(2):
        (tmp_path / f"design_{n}.pdb").write_text(f"orig main {n}")
        (tmp_path / "traj" / f"design_{n}_pX0_traj.pdb").write_text(f"orig px0 {n}")
        (tmp_path / "traj" / f"design_{n}_Xt-1_traj.pdb").write_text(f"orig xt1 {n}")

    PdbPostProcessor().fix_outputs(tmp_path, "design", num_designs=2, contigs=contigs)

    assert len(calls) == 6  # 3 paths x 2 designs
    assert all(c[1] == contigs for c in calls)

    for n in range(2):
        assert (tmp_path / f"design_{n}.pdb").read_text() == f"ORIG MAIN {n}"
        assert (tmp_path / "traj" / f"design_{n}_pX0_traj.pdb").read_text() == f"ORIG PX0 {n}"
        assert (tmp_path / "traj" / f"design_{n}_Xt-1_traj.pdb").read_text() == f"ORIG XT1 {n}"


def test_content_rewritten_not_appended(tmp_path, monkeypatch):
    (tmp_path / "traj").mkdir()
    monkeypatch.setattr(_colabdesign, "fix_pdb", lambda s, c: "REPLACED")

    (tmp_path / "d_0.pdb").write_text("original content that should be gone")
    (tmp_path / "traj" / "d_0_pX0_traj.pdb").write_text("x")
    (tmp_path / "traj" / "d_0_Xt-1_traj.pdb").write_text("x")

    PdbPostProcessor().fix_outputs(tmp_path, "d", num_designs=1, contigs=[])

    content = (tmp_path / "d_0.pdb").read_text()
    assert content == "REPLACED"
    assert "original content" not in content
