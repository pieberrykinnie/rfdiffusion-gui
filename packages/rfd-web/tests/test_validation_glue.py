from __future__ import annotations

import pytest
from rfd_web.routes.submit import parse_form_to_request
from rfd_web.config import WebConfig

def test_parse_form_to_request_valid():
    form_data = {
        "name": "test",
        "mode": "unconditional",
        "contigs": "50",
        "iterations": "50",
        "num_designs": "1",
        "partition": "gpu"
    }
    config = WebConfig.from_env()
    
    req = parse_form_to_request(form_data, config)
    assert req.name == "test"
    assert req.contigs == "50"


def test_parse_form_to_request_with_all_web_form_fields():
    from rfd_core.symmetry import SymmetryKind
    form_data = {
        "name": "binder_run",
        "contigs": "A:50",
        "pdb": "6MRR",
        "hotspots": "A10,A12",
        "iterations": "100",
        "num_designs": "4",
        "symmetry_kind": "cyclic",
        "symmetry_order": "3",
        "chains": "A,B",
        "add_potential": "true",
        "partial_T": "20",
        "use_beta_model": "on",
        "live_preview": "true",
        "num_seqs": "16",
        "mpnn_sampling_temp": "0.2",
        "rm_aa": "C",
        "num_recycles": "3",
        "use_soluble_mpnn": "true",
        "initial_guess": "true",
        "use_multimer": "true",
        "slurm_partition": "gpu",
        "slurm_account": "def-lab",
        "slurm_walltime": "01:00:00",
        "slurm_gpus": "2",
        "slurm_cpus_per_task": "4",
        "slurm_mem_per_cpu": "8G",
    }
    config = WebConfig.from_env()
    req = parse_form_to_request(form_data, config)
    assert req.name == "binder_run"
    assert req.contigs == "A:50"
    assert req.pdb == "6MRR"
    assert req.hotspot == "A10,A12"
    assert req.iterations == 100
    assert req.num_designs == 4
    assert req.symmetry == SymmetryKind.CYCLIC
    assert req.order == 3
    assert req.chains == "A,B"
    assert req.add_potential is True
    assert req.partial_T == "20"
    assert req.use_beta_model is True
    assert req.live_preview is True
    assert req.num_seqs == 16
    assert req.mpnn_sampling_temp == 0.2
    assert req.rm_aa == "C"
    assert req.num_recycles == 3
    assert req.use_soluble_mpnn is True
    assert req.initial_guess is True
    assert req.use_multimer is True
    assert req.partition == "gpu"
    assert req.account == "def-lab"
    assert req.walltime == "01:00:00"
    assert req.gpus == 2
    assert req.cpus_per_task == 4
    assert req.mem_per_cpu == "8G"

