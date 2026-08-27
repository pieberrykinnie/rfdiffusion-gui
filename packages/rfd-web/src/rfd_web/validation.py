from __future__ import annotations

from typing import Any, Optional

from rfd_web.config import WebConfig
from rfd_core.models import DesignRequest
from rfd_core.validation import ValidationOutcome


def parse_form_to_request(form_data: dict[str, Any], config: WebConfig) -> DesignRequest:
    """Converts string/form inputs to typed DesignRequest with defaults from config."""
    
    def get_bool(key: str, default: bool) -> bool:
        val = form_data.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('on', 'true', '1', 'yes')
        return bool(val)
    
    def get_int(key: str, default: int) -> int:
        val = form_data.get(key)
        if val is None or val == "":
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
            
    def get_float(key: str, default: float) -> float:
        val = form_data.get(key)
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_str_optional(*keys: str) -> Optional[str]:
        for key in keys:
            val = form_data.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def get_first_str(*keys: str, default: str = "") -> str:
        for key in keys:
            val = form_data.get(key)
            if val is not None and isinstance(val, str) and val.strip():
                return val.strip()
        return default
        
    num_designs = get_int("num_designs", 1)
    
    # We must construct SymmetryKind enum from the str
    symmetry_str = get_str_optional("symmetry", "symmetry_kind")
    from rfd_core.symmetry import SymmetryKind
    symmetry = SymmetryKind.NONE
    if symmetry_str:
        try:
            symmetry = SymmetryKind(symmetry_str.lower())
        except ValueError:
            pass
            
    order = get_int("order", get_int("symmetry_order", 1))
    
    req = DesignRequest(
        name=get_first_str("name", default="design"),
        contigs=get_first_str("contigs", default=""),
        pdb=get_str_optional("pdb", "pdb_id", "template"),
        iterations=get_int("iterations", 50),
        num_designs=num_designs,
        hotspot=get_str_optional("hotspot", "hotspots"),
        symmetry=symmetry,
        order=order,
        chains=get_str_optional("chains"),
        add_potential=get_bool("add_potential", False),
        partial_T=get_first_str("partial_T", default="auto"),
        use_beta_model=get_bool("use_beta_model", False),
        live_preview=get_bool("live_preview", True),
        num_seqs=get_int("num_seqs", 8),
        mpnn_sampling_temp=get_float("mpnn_sampling_temp", 0.1),
        rm_aa=get_str_optional("rm_aa") or "C",
        use_soluble_mpnn=get_bool("use_soluble_mpnn", False),
        initial_guess=get_bool("initial_guess", False),
        num_recycles=get_int("num_recycles", 1),
        use_multimer=get_bool("use_multimer", False),
        partition=get_first_str("slurm_partition", "partition", default=config.default_partition),
        account=get_str_optional("slurm_account", "account") or config.default_account,
        walltime=get_first_str("slurm_walltime", "walltime", default=config.default_walltime),
        gpus=get_int("slurm_gpus", get_int("gpus", config.default_gpus)),
        cpus_per_task=get_int("slurm_cpus_per_task", get_int("cpus_per_task", config.default_cpus_per_task)),
        mem_per_cpu=get_first_str("slurm_mem_per_cpu", "mem_per_cpu", default=config.default_mem_per_cpu),
    )
    return req

def format_validation_errors(outcome: ValidationOutcome) -> list[str]:
    """Format ValidationOutcome into a list of human-readable error messages."""
    return list(outcome.errors)
