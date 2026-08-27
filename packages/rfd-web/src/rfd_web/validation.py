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
        if not val:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
            
    def get_float(key: str, default: float) -> float:
        val = form_data.get(key)
        if not val:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_str_optional(key: str) -> Optional[str]:
        val = form_data.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
        return None
        
    num_designs = get_int("num_designs", 1)
    
    # We must construct SymmetryKind enum from the str
    symmetry_str = get_str_optional("symmetry")
    from rfd_core.symmetry import SymmetryKind
    symmetry = SymmetryKind.NONE
    if symmetry_str:
        try:
            symmetry = SymmetryKind(symmetry_str.lower())
        except ValueError:
            pass
            
    order = get_int("order", 1)
    
    req = DesignRequest(
        name=form_data.get("name", "design").strip(),
        contigs=form_data.get("contigs", "").strip(),
        iterations=get_int("iterations", 50),
        num_designs=num_designs,
        hotspot=get_str_optional("hotspot"),
        symmetry=symmetry,
        order=order,
        chains=get_str_optional("chains"),
        add_potential=get_bool("add_potential", False),
        partial_T=form_data.get("partial_T", "auto").strip() or "auto",
        use_beta_model=get_bool("use_beta_model", False),
        live_preview=get_bool("live_preview", True),
        partition=form_data.get("partition", config.default_partition),
        account=form_data.get("account", config.default_account),
        walltime=form_data.get("walltime", config.default_walltime),
        gpus=get_int("gpus", config.default_gpus),
        cpus_per_task=get_int("cpus_per_task", config.default_cpus_per_task),
        mem_per_cpu=form_data.get("mem_per_cpu", config.default_mem_per_cpu)
    )
    return req

def format_validation_errors(outcome: ValidationOutcome) -> list[str]:
    """Format ValidationOutcome into a list of human-readable error messages."""
    return list(outcome.errors)
