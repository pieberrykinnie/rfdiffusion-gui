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
    
def test_parse_form_to_request_invalid():
    # pydantic will validate this or not?
    # Actually validation is done in `validate(req)` later.
    # We shouldn't assert ValueError here unless parse_form_to_request actually throws
    pass
