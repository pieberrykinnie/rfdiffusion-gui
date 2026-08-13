from pathlib import Path

from rfd_runner.config import RunnerConfig


def test_defaults_with_empty_env():
    config = RunnerConfig.from_env(env={})
    assert config.step_timeout_seconds == 1800
    assert config.poll_interval_ms == 100
    assert config.frame_every_n == 5
    assert config.fork_root == Path("/opt/RFdiffusion")
    assert config.models_dir == Path("/opt/RFdiffusion/models")
    assert config.af_params_dir == Path("/opt/weights/alphafold")
    assert config.ananas_bin == Path("/opt/weights/bin/ananas")
    assert config.python_bin == Path("/app/RFdiffusion/.venv/bin/python")


def test_every_field_overridable_via_env():
    env = {
        "RFD_STEP_TIMEOUT_SECONDS": "60",
        "RFD_POLL_INTERVAL_MS": "50",
        "RFD_FRAME_EVERY_N": "10",
        "RFD_FORK": "/custom/fork",
        "RFD_MODELS": "/custom/models",
        "RFD_AF_PARAMS": "/custom/af",
        "ANANAS_BIN": "/custom/ananas",
    }
    config = RunnerConfig.from_env(env=env)
    assert config.step_timeout_seconds == 60
    assert config.poll_interval_ms == 50
    assert config.frame_every_n == 10
    assert config.fork_root == Path("/custom/fork")
    assert config.models_dir == Path("/custom/models")
    assert config.af_params_dir == Path("/custom/af")
    assert config.ananas_bin == Path("/custom/ananas")
    # python_bin is not overridden by any env var -- matches the container's fixed venv path.
    assert config.python_bin == Path("/app/RFdiffusion/.venv/bin/python")
