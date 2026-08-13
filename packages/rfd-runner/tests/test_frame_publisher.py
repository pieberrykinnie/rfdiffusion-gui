import pytest

from rfd_runner.frame_publisher import FramePublisher


def test_publishes_only_every_n_steps(tmp_path):
    frame = tmp_path / "src.pdb"
    frame.write_text("ATOM ...")

    publisher = FramePublisher(tmp_path, every_n=5, enabled=True)

    assert publisher.maybe_publish(0, frame) == tmp_path / "current_frame.pdb"
    assert publisher.maybe_publish(1, frame) is None
    assert publisher.maybe_publish(4, frame) is None
    assert publisher.maybe_publish(5, frame) == tmp_path / "current_frame.pdb"


def test_disabled_never_writes(tmp_path):
    frame = tmp_path / "src.pdb"
    frame.write_text("ATOM ...")

    publisher = FramePublisher(tmp_path, every_n=1, enabled=False)

    assert publisher.maybe_publish(0, frame) is None
    assert not (tmp_path / "current_frame.pdb").exists()


def test_target_path_and_atomicity(tmp_path):
    frame = tmp_path / "src.pdb"
    frame.write_text("frame content step 0")

    publisher = FramePublisher(tmp_path, every_n=1, enabled=True)
    result = publisher.maybe_publish(0, frame)

    target = tmp_path / "current_frame.pdb"
    assert result == target
    assert target.read_text() == "frame content step 0"
    # No leftover temp files after a successful publish.
    assert list(tmp_path.glob(".*current_frame.pdb*.tmp")) == []

    frame.write_text("frame content step 1")
    publisher.maybe_publish(1, frame)
    assert target.read_text() == "frame content step 1"


def test_temp_file_cleaned_up_when_replace_fails(tmp_path, monkeypatch):
    import rfd_runner.frame_publisher as fp_module

    frame = tmp_path / "src.pdb"
    frame.write_text("frame content")

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(fp_module.os, "replace", failing_replace)

    publisher = FramePublisher(tmp_path, every_n=1, enabled=True)
    with pytest.raises(OSError):
        publisher.maybe_publish(0, frame)

    # No leftover .tmp files after the cleanup path runs.
    assert list(tmp_path.glob(".*current_frame.pdb*.tmp")) == []
    assert not (tmp_path / "current_frame.pdb").exists()


def test_original_error_propagates_even_if_cleanup_unlink_also_fails(tmp_path, monkeypatch):
    import rfd_runner.frame_publisher as fp_module

    frame = tmp_path / "src.pdb"
    frame.write_text("frame content")

    monkeypatch.setattr(
        fp_module.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("replace failed"))
    )
    monkeypatch.setattr(
        fp_module.os, "unlink", lambda path: (_ for _ in ()).throw(OSError("unlink also failed"))
    )

    publisher = FramePublisher(tmp_path, every_n=1, enabled=True)
    with pytest.raises(OSError, match="replace failed"):
        publisher.maybe_publish(0, frame)
