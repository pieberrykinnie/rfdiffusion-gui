"""ProteinMPNN/AlphaFold validation subprocess execution.

Builds the designability_test.py argv exactly per business-logic-model.md section 2 steps 12-13
(transcribed from reference/diffusion.py lines 503-517), then runs it to completion -- unlike
InferenceExecutor, there is no per-step dump to poll here, so this reuses the SAME KIND of
popen_factory injection seam rather than InferenceExecutor's step-polling loop.

business-rules.md section 6: cwd MUST be RunnerConfig.af_params_dir -- not a convenience default.
ColabDesign's vendored AlphaFold parameter loader (data_dir=".") can only find the staged params
this way, since designability_test.py exposes no flag to override it (business-logic-model.md
section 1.2).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from rfd_core import DesignRequest

from .config import RunnerConfig
from .inference_executor import InferenceResult, PopenFactory, _last_4kb


class ValidationExecutor:
    def run_validation(
        self,
        run_dir: Path,
        name: str,
        normalised_contigs: List[str],
        copies: int,
        request: DesignRequest,
        *,
        popen_factory: Optional[PopenFactory] = None,
        cwd: Optional[Path] = None,
    ) -> InferenceResult:
        run_dir = Path(run_dir)
        popen_factory = popen_factory if popen_factory is not None else subprocess.Popen
        config = RunnerConfig.from_env()
        cwd = cwd if cwd is not None else config.af_params_dir

        contigs_str = ":".join(normalised_contigs)  # notebook line 503

        val_argv = [
            str(config.python_bin),
            "-m",
            "colabdesign.rf.designability_test",
            f"--pdb={run_dir}/{name}_0.pdb",
            f"--loc={run_dir}/{name}",
            f"--contig={contigs_str}",
            f"--copies={copies}",
            f"--num_seqs={request.num_seqs}",
            f"--num_recycles={request.num_recycles}",
            f"--rm_aa={request.rm_aa or ''}",
            f"--mpnn_sampling_temp={request.mpnn_sampling_temp}",
            f"--num_designs={request.num_designs}",
        ]
        if request.initial_guess:
            val_argv.append("--initial_guess")
        if request.use_multimer:
            val_argv.append("--use_multimer")
        if request.use_soluble_mpnn:
            val_argv.append("--use_soluble")

        proc = popen_factory(
            val_argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        _stdout, stderr = proc.communicate()
        return InferenceResult(exit_code=proc.returncode, stderr_tail=_last_4kb(stderr))
