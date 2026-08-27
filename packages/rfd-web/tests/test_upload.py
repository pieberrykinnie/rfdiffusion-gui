from __future__ import annotations

import pytest
import io
from fastapi import UploadFile, HTTPException
from rfd_web.upload import save_upload

@pytest.mark.asyncio
async def test_save_upload(tmp_path):
    file_content = b"ATOM  1"
    upload = UploadFile(filename="test.pdb", file=io.BytesIO(file_content))
    
    target_path = await save_upload(upload, tmp_path)
    
    assert target_path.exists()
    assert target_path.read_bytes() == file_content
    
@pytest.mark.asyncio
async def test_save_upload_size_limit(tmp_path):
    # Create a 6MB file, limit is 5MB
    file_content = b"0" * (6 * 1024 * 1024)
    upload = UploadFile(filename="test.pdb", file=io.BytesIO(file_content))
    
    with pytest.raises(HTTPException) as exc:
        await save_upload(upload, tmp_path, max_bytes=5_000_000)
    assert exc.value.status_code == 413
