from __future__ import annotations

import os
import shutil
from typing import Optional

import uvicorn

from rfd_core.paths import PathLayout
from rfd_web import CliSlurmAdapter, FakeSlurmAdapter, WebConfig, create_app

def main() -> None:
    host = os.environ.get("RFD_BIND_HOST", "127.0.0.1")
    port_str = os.environ.get("RFD_BIND_PORT", "8080")
    try:
        port = int(port_str)
    except ValueError:
        port = 8080

    layout = PathLayout.from_env()
    config = WebConfig.from_env()

    if shutil.which("sinfo"):
        slurm = CliSlurmAdapter()
        adapter_type = "CliSlurmAdapter"
    else:
        slurm = FakeSlurmAdapter()
        adapter_type = "FakeSlurmAdapter"
        print("*" * 60)
        print("WARNING: 'sinfo' not found in PATH.")
        print("Using FakeSlurmAdapter. Slurm integration is disabled.")
        print("*" * 60)

    app = create_app(config, slurm, layout)

    print(f"Starting rfdiffusion-gui on http://{host}:{port}")
    print(f"Active Slurm adapter: {adapter_type}")

    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
