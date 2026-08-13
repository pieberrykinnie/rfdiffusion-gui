"""CLI entry point. Invoked by containers/rfdiffusion.def's %runscript as
`python -m rfd_runner "$@"`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .orchestrator import Stage, main


def _parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rfd_runner")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--stage", choices=[s.value for s in Stage], default=Stage.ALL.value
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    sys.exit(main(args.run_dir, stage=Stage(args.stage)))
