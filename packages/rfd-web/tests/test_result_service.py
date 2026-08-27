from __future__ import annotations

import pytest
from rfd_web.services.result import ResultService
from rfd_web.persistence.reader import RunDirectoryReader

def test_result_service_get_structure(layout, written_record):
    written_record(run_id="run_123")
    
    run_dir = layout.run_dir("run_123")
    (run_dir / "design_0.pdb").write_text("ATOM")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    struct_path = service.get_structure("run_123", 0)
    assert struct_path is not None
    assert struct_path.exists()
    
def test_result_service_get_result_zip(layout, written_record):
    written_record(run_id="run_123")
    run_dir = layout.run_dir("run_123")
    (run_dir / "run_123_results.zip").write_text("zipcontent")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    archive_path = service.get_result_zip("run_123")
    assert archive_path is not None
    assert archive_path.exists()
