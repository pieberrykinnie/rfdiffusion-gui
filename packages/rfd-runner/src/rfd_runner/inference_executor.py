"""RFdiffusion subprocess execution and per-step progress polling.

Transcribed from reference/diffusion.py's run() (lines 144-225), adapted for subprocess.Popen
instead of os.system + raw PID tracking (Popen.poll() replaces the notebook's os.kill(pid, 0)
liveness trick entirely -- no PID-file dance needed), and for an injected dump_dir instead of the
notebook's hardcoded /dev/shm. See business-logic-model.md section 3 for the full algorithm and
business-rules.md section 2 for the per-step timeout rationale.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

# Distinguishes a stalled step from the subprocess's own exit codes -- matches the `timeout`
# command's own convention (128 + SIGTERM's 9... no: conventionally 124) so it reads as
# "exceeded a deadline" to anyone who has used GNU coreutils' timeout.
STALL_EXIT_CODE = 124

_DEFAULT_STEP_TIMEOUT_SECONDS = 1800
_DEFAULT_POLL_INTERVAL_MS = 100

OnStepCallback = Callable[[int, int, Path], None]
PopenFactory = Callable[..., "subprocess.Popen[str]"]


@dataclass(frozen=True)
class InferenceResult:
    exit_code: int
    stderr_tail: str  # last ~4KB of stderr, for FAILED error messages


def _last_4kb(text: Optional[str]) -> str:
    if not text:
        return ""
    return text[-4096:]


def _dump_ends_with_ter(path: Path) -> bool:
    try:
        content = path.read_text()
    except OSError:
        return False
    return content[-3:] == "TER"


class InferenceExecutor:
    def run_inference(
        self,
        argv: List[str],
        total_steps: int,
        num_designs: int,
        dump_dir: Path,
        on_step: OnStepCallback,
        *,
        popen_factory: PopenFactory = subprocess.Popen,
        timeout_seconds: Optional[int] = None,
        poll_interval_ms: Optional[int] = None,
    ) -> InferenceResult:
        dump_dir = Path(dump_dir)
        timeout_seconds = timeout_seconds if timeout_seconds is not None else _DEFAULT_STEP_TIMEOUT_SECONDS
        poll_interval_s = (
            poll_interval_ms if poll_interval_ms is not None else _DEFAULT_POLL_INTERVAL_MS
        ) / 1000.0

        # Clear any stale dumps from a previous attempt (notebook lines 165-168).
        for n in range(total_steps):
            stale = dump_dir / f"{n}.pdb"
            if stale.is_file():
                stale.unlink()

        proc = popen_factory(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            for design_i in range(num_designs):
                for step in range(total_steps):
                    dump_path = dump_dir / f"{step}.pdb"
                    deadline = time.monotonic() + timeout_seconds

                    while True:
                        if proc.poll() is not None:
                            if _dump_ends_with_ter(dump_path):
                                break  # fast final write -- treated as success for this step
                            _stdout, stderr = proc.communicate()
                            return InferenceResult(
                                exit_code=proc.returncode, stderr_tail=_last_4kb(stderr)
                            )

                        if _dump_ends_with_ter(dump_path):
                            on_step(design_i, step, dump_path)
                            dump_path.unlink()
                            break

                        if time.monotonic() > deadline:
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait()
                            return InferenceResult(
                                exit_code=STALL_EXIT_CODE,
                                stderr_tail=f"step {step} exceeded {timeout_seconds}s",
                            )

                        time.sleep(poll_interval_s)

            _stdout, stderr = proc.communicate()
            return InferenceResult(exit_code=proc.returncode, stderr_tail=_last_4kb(stderr))
        except BaseException:
            # Mirrors the notebook's `except KeyboardInterrupt: os.kill(pid, SIGTERM)` (line 223),
            # generalised to any exception/signal the runner itself receives while polling --
            # there is no interactive kernel to interrupt inside a Slurm job, so this is the
            # runner's own responsibility. PipelineOrchestrator's SIGTERM handler (business-rules.md
            # section 4) is what actually delivers SIGTERM to the runner process; this ensures the
            # child is not left orphaned when that happens.
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            raise
