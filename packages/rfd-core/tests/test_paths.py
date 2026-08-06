from pathlib import Path

from rfd_core.paths import PathLayout


class TestDefaults:
    def test_defaults_derive_from_home(self):
        layout = PathLayout.from_env(env={"HOME": "/home/testuser"})
        assert layout.weights_root == Path("/home/testuser/rfd-weights")
        assert layout.image_path == Path("/home/testuser/rfd-images/rfdiffusion.sif")
        assert layout.output_root == Path("/home/testuser/rfd-runs")
        assert layout.database_path == Path(
            "/home/testuser/.local/share/rfdgui/runs.sqlite"
        )


class TestOverrides:
    def test_explicit_env_vars_override_defaults(self):
        layout = PathLayout.from_env(
            env={
                "HOME": "/home/testuser",
                "RFD_WEIGHTS": "/project/def-cardona/testuser/rfd-weights",
                "RFD_OUTPUT_ROOT": "/project/def-cardona/testuser/rfd-runs",
            }
        )
        assert layout.weights_root == Path("/project/def-cardona/testuser/rfd-weights")
        assert layout.output_root == Path("/project/def-cardona/testuser/rfd-runs")
        # database_path was not overridden -- still defaults under $HOME,
        # per the deliberate "keep SQLite off Lustre" guidance.
        assert layout.database_path == Path(
            "/home/testuser/.local/share/rfdgui/runs.sqlite"
        )


class TestRunDir:
    def test_run_dir_is_under_output_root(self):
        layout = PathLayout.from_env(env={"HOME": "/home/testuser"})
        assert layout.run_dir("abc123") == Path("/home/testuser/rfd-runs/abc123")
