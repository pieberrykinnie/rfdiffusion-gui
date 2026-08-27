from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import UploadFile, HTTPException

async def save_upload(upload: UploadFile, run_dir: Path, max_bytes: int = 50_000_000) -> Path:
    """
    Validates .pdb extension, checks size limit, writes atomically to run_dir / "template.pdb".
    Returns the path.
    """
    if not upload.filename or not upload.filename.lower().endswith(".pdb"):
        raise HTTPException(status_code=400, detail="Invalid file extension. Only .pdb files are allowed.")
    
    target_path = run_dir / "template.pdb"
    
    # Check if run_dir exists
    run_dir.mkdir(parents=True, exist_ok=True)
    
    bytes_read = 0
    
    # Write to a temporary file first for atomic write
    try:
        with NamedTemporaryFile(delete=False, dir=run_dir, suffix=".tmp") as tmp_file:
            tmp_path = Path(tmp_file.name)
            while chunk := await upload.read(8192):
                bytes_read += len(chunk)
                if bytes_read > max_bytes:
                    tmp_path.unlink()
                    raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {max_bytes} bytes.")
                tmp_file.write(chunk)
                
        # Move temporary file to target path
        shutil.move(str(tmp_path), str(target_path))
    except Exception as e:
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink()
        raise e
        
    return target_path
