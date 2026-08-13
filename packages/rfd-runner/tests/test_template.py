from rfd_runner.template import TemplateResolver


def test_local_path_pass_through_no_fetch_call(tmp_path):
    local = tmp_path / "mine.pdb"
    local.write_text("ATOM ...")
    calls = []

    result = TemplateResolver().resolve_template(str(local), tmp_path, fetch=calls.append)

    assert result == local
    assert calls == []


def test_none_or_empty_pdb_returns_none(tmp_path):
    calls = []
    assert TemplateResolver().resolve_template(None, tmp_path, fetch=calls.append) is None
    assert TemplateResolver().resolve_template("", tmp_path, fetch=calls.append) is None
    assert calls == []


def test_four_char_code_builds_rcsb_wget_and_gunzip_argv(tmp_path):
    calls = []

    def fake_fetch(argv):
        calls.append(argv)
        if argv[0] == "wget":
            (tmp_path / "1abc.pdb1.gz").write_bytes(b"\x1f\x8b")
        elif argv[0] == "gunzip":
            (tmp_path / "1abc.pdb1.gz").unlink()
            (tmp_path / "1abc.pdb1").write_text("ATOM ...")

    result = TemplateResolver().resolve_template("1abc", tmp_path, fetch=fake_fetch)

    assert result == tmp_path / "1abc.pdb1"
    assert len(calls) == 2
    wget_argv, gunzip_argv = calls
    assert wget_argv[0] == "wget"
    assert "https://files.rcsb.org/download/1abc.pdb1.gz" in wget_argv
    assert gunzip_argv[0] == "gunzip"
    assert str(tmp_path / "1abc.pdb1.gz") in gunzip_argv


def test_non_four_char_code_builds_alphafold_db_argv(tmp_path):
    calls = []

    def fake_fetch(argv):
        calls.append(argv)
        (tmp_path / "AF-P12345-F1-model_v3.pdb").write_text("ATOM ...")

    result = TemplateResolver().resolve_template("P12345", tmp_path, fetch=fake_fetch)

    assert result == tmp_path / "AF-P12345-F1-model_v3.pdb"
    assert len(calls) == 1
    assert calls[0][0] == "wget"
    assert "https://alphafold.ebi.ac.uk/files/AF-P12345-F1-model_v3.pdb" in calls[0]


def test_file_already_present_short_circuits_fetch_rcsb(tmp_path):
    (tmp_path / "1abc.pdb1").write_text("ATOM ...")
    calls = []

    result = TemplateResolver().resolve_template("1abc", tmp_path, fetch=calls.append)

    assert result == tmp_path / "1abc.pdb1"
    assert calls == []


def test_file_already_present_short_circuits_fetch_alphafold(tmp_path):
    (tmp_path / "AF-P12345-F1-model_v3.pdb").write_text("ATOM ...")
    calls = []

    result = TemplateResolver().resolve_template("P12345", tmp_path, fetch=calls.append)

    assert result == tmp_path / "AF-P12345-F1-model_v3.pdb"
    assert calls == []


def test_default_fetch_invokes_subprocess_run(monkeypatch):
    from rfd_runner import template as template_module

    calls = []
    monkeypatch.setattr(
        template_module.subprocess, "run", lambda argv, check: calls.append((argv, check))
    )

    template_module._default_fetch(["wget", "http://example.org/x.pdb"])

    assert calls == [(["wget", "http://example.org/x.pdb"], True)]
