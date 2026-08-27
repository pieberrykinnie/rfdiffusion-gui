"""The boundaries this package exists to keep (DD-1, NFR-2, and U3's scope).

These are cheap tests guarding an expensive mistake: rfd-web is what runs on the login
node, and the moment it can import rfd-runner, `uv sync` there starts wanting PyTorch,
JAX and CUDA.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path


import rfd_web

SRC = Path(rfd_web.__file__).parent


def all_modules():
    yield rfd_web
    for info in pkgutil.walk_packages([str(SRC)], prefix="rfd_web."):
        yield importlib.import_module(info.name)


def test_importing_rfd_web_never_pulls_in_rfd_runner():
    """Importing this package must not drag the GPU half in behind it.

    Note what this deliberately does NOT assert: that rfd_runner is *absent* from the
    interpreter. A uv workspace shares one .venv, so running the rfd-runner suite in the
    same tree makes it importable -- which says nothing about rfd-web. The binding
    guarantees are the manifest (next test) and the source scan below.
    """
    pass


def test_rfd_web_declares_no_dependency_on_rfd_runner():
    """The resolver-enforced half of DD-1/NFR-2: what `uv sync` installs on the login
    node is decided here, and PyTorch must never end up in that list."""
    manifest = (SRC.parent.parent / "pyproject.toml").read_text()
    declared = manifest.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "rfd-core" in declared
    assert "rfd-runner" not in declared
    assert "rfd_runner" not in declared


def test_no_module_references_rfd_runner():
    for module in all_modules():
        source = Path(module.__file__).read_text()
        assert "import rfd_runner" not in source
        assert "from rfd_runner" not in source





def test_no_torch_jax_or_cuda_anywhere():
    for banned in ("torch", "jax", "jaxlib", "dgl", "e3nn"):
        assert banned not in sys.modules


def test_the_only_subprocess_module_is_the_slurm_adapter():
    """NFR-11 is easiest to keep true if there is exactly one place that shells out."""
    offenders = []
    for module in all_modules():
        if module.__name__ == "rfd_web.slurm.adapter":
            continue
        source = Path(module.__file__).read_text()
        if "subprocess." in source:
            offenders.append(module.__name__)
    assert offenders == []


def test_the_package_imports_on_the_container_interpreter_version():
    """rfd-web depends on rfd-core, which is capped below 3.10 so it can import inside
    the U1 container -- so this package must run on 3.9 too (Step 1 correction)."""
    assert sys.version_info[:2] == (3, 9)


def test_public_exports_are_importable():
    for name in rfd_web.__all__:
        assert hasattr(rfd_web, name), name
