# U2b Runner — Business Logic Model

`rfd-runner` executes inside the Apptainer image, on a GPU compute node. It is the in-process
successor to the notebook's cell sequence, driven by `PipelineOrchestrator` (C-20, `services.md` S-4).
This document covers what wasn't already fully specified: the parts requiring real research into
RFdiffusion's/ColabDesign's actual runtime behaviour, verified against source rather than assumed.

**Depends on `rfd-core`** for `ContigSpec`, `infer_mode`, `resolve_symmetry`, `plan_iterations`,
`build_inference_argv`, `RunRecord`, `ProgressState`, `PathLayout`.

---

## 1. Two Verified Facts That Shape This Design

### 1.1 Hydra's `config_path` resolves relative to the script file, not cwd

`run_inference.py`'s decorator is `@hydra.main(version_base=None, config_path="config/inference",
config_name="base")`. Hydra resolves a relative `config_path` **relative to the decorated script's
own file location** — this is standard `@hydra.main` behaviour, not container-specific. So:

```
python /opt/RFdiffusion/run_inference.py <overrides>
```

correctly finds `/opt/RFdiffusion/config/inference/base.yaml` (and `config/symmetry.yaml` for
`--config-name symmetry`) **regardless of the subprocess's working directory**. `InferenceExecutor`
does not need to `cd` into `/opt/RFdiffusion` — it can run with `cwd` set to the run directory, which
is more convenient for relative output paths.

### 1.2 `designability_test.py` requires a specific working directory — this is not configurable

`designability_test.py` never exposes a `data_dir` flag. AlphaFold parameter loading
(`get_model_haiku_params`, vendored in `colabdesign/af/alphafold/model/data.py`) defaults to
`data_dir="."` and tries, in order:
```
{cwd}/params/params_{model_name}.npz
{cwd}/params_{model_name}.npz          <- matches our staged layout
{cwd}/params/{model_name}.npz
{cwd}/{model_name}.npz
```

`stage-weights.sh` extracts the AlphaFold tar flat into `$RFD_WEIGHTS/alphafold/` (matching the
official DeepMind download script's convention of naming the *container* directory `params/`, then
extracting flat `.npz` files into it) — so `params_model_1_ptm.npz` lands directly at
`$RFD_WEIGHTS/alphafold/params_model_1_ptm.npz`. This matches fallback #2 above **only if the
validation subprocess's `cwd` is `/opt/weights/alphafold`** (the bind-mounted, read-only mount of
`$RFD_WEIGHTS/alphafold`).

**This is not optional and not configurable via a flag** — `ValidationExecutor` (C-18) must launch
`designability_test.py` with `cwd=/opt/weights/alphafold`. Its own outputs (`best.pdb`,
`mpnn_results.csv`, per-design PDBs) go to `--loc=<run_dir>/...`, which is independent of `cwd` and
fine to be on a read-only-mounted-elsewhere filesystem, since none of `designability_test.py`'s
*writes* touch `cwd`.

### 1.3 Consequence: G-13 ("stage out before job end") is satisfied by construction, not by a copy step

Re-reading the notebook's own option assembly (lines 234, 330) shows it already separated two
different RFdiffusion paths:
- `inference.output_prefix` — **final** per-design backbones and trajectories
- `inference.dump_pdb_path` — **ephemeral** per-step live-progress dumps only

The notebook pointed the first at a persistent-ish location and the second at `/dev/shm`. In this
port, the same split does the work: `output_prefix` points directly at the **persistent, bind-mounted
run directory** (`/opt/outputs/{run_id}/...`), and `dump_pdb_path` points at **`/scratch`**
(`$TMPDIR`). Nothing ever needs to be copied out of scratch at job end — final outputs are written to
persistent storage from the moment they exist. The only thing genuinely built at the end is the
**result zip** (FR-31), which is new output, not a relocation.

---

## 2. `PipelineOrchestrator` — Full Control Flow (`--stage all`)

Elaborates `services.md` S-4 with the facts above folded in.

```
1.  Load RunRecord from run_dir (written by SubmissionService before the job was submitted).
    Mark backbone_state = RUNNING; save.

2.  spec = ContigSpec.parse(request.contigs)          [rfd-core]
    mode = infer_mode(spec)                            [rfd-core]

3.  symmetry_plan = resolve_symmetry(request.symmetry, request.order, request.add_potential)
                                                         [rfd-core]

4.  IF mode in (FIXED, PARTIAL):
        template_path = TemplateResolver.resolve(request.pdb, run_dir)   -- RCSB / AlphaFold DB /
                                                                             local / pre-uploaded
        pdb_str = pdb_to_string(template_path, chains=request.chains)     [ColabDesign]

        IF symmetry_plan.deferred:                     -- symmetry == AUTO
            IF ananas binary present:
                detection = SymmetryDetector.detect(pdb_str, run_dir)     -- may be None (not found)
                symmetry_plan = apply_detected_group(symmetry_plan, detection.group if detection else None)
                                                         [rfd-core]
                pdb_str = detection.asymmetric_unit_pdb_str if detection else pdb_str
            ELSE:
                FAIL run with a clear, actionable error (business-rules.md section 3) --
                never a bare exception, never a silent fallback to symmetry=none.

        ELIF mode == FIXED:
            pdb_str = pdb_to_string(pdb_str, chains=spec.fixed_chains)    [ColabDesign]

        write pdb_str to run_dir/input.pdb
        parsed_pdb = parse_pdb(run_dir/input.pdb)        [RFdiffusion inference.utils]

        normalised_contigs = ContigNormaliser.normalise(spec, mode, parsed_pdb)
                                                         [ColabDesign fix_contigs / fix_partial_contigs]
    ELSE:  -- mode == FREE
        parsed_pdb = None
        normalised_contigs = ContigNormaliser.normalise(spec, mode, None)  -- fix_contigs(contigs, None)

    IF symmetry_plan.copies > 1:
        normalised_contigs = normalised_contigs * symmetry_plan.copies    -- notebook line 327

5.  iteration_plan = plan_iterations(mode, request.iterations, request.partial_T)   [rfd-core]

6.  argv = build_inference_argv(                        [rfd-core]
                mode=mode, symmetry=symmetry_plan, iteration=iteration_plan,
                normalised_contigs=normalised_contigs,
                output_prefix=f"{run_dir}/{request.name}",      -- PERSISTENT (section 1.3)
                num_designs=request.num_designs,
                dump_pdb_path="/scratch",                        -- EPHEMERAL (section 1.3)
                input_pdb=(f"{run_dir}/input.pdb" if mode != FREE else None),
                hotspot=request.hotspot,
                use_beta_model=request.use_beta_model,
                beta_ckpt_path="/opt/RFdiffusion/models/Complex_beta_ckpt.pt")

7.  mkdir -p /scratch/schedules                          -- REQUIRED before invoking run_inference.py;
                                                              the fork does os.mkdir() on the symlinked
                                                              path at import time (U1 finding, section 1
                                                              of infrastructure-design.md 8.1d)

8.  result = InferenceExecutor.run(
                argv=["/app/RFdiffusion/.venv/bin/python", "/opt/RFdiffusion/run_inference.py"] + argv,
                total_steps=iteration_plan.steps, num_designs=request.num_designs,
                dump_dir="/scratch",
                on_step=lambda design_i, step, frame_path: (
                    ProgressReporter.update_step("backbone", design_i, step, iteration_plan.steps),
                    FramePublisher.maybe_publish(step, frame_path) if request.live_preview else None
                ))

    IF result.exit_code != 0:
        mark backbone_state = FAILED, error = result.stderr_tail, exit_code = result.exit_code; save.
        RETURN (validate_state stays PENDING -> effectively SKIPPED for reporting)

9.  PdbPostProcessor.fix_outputs(run_dir, request.name, request.num_designs, normalised_contigs)
                                                         [ColabDesign fix_pdb, per design and trajectory]

10. Update RunRecord: mode, normalised_contigs, copies=symmetry_plan.copies,
    backbone_state = COMPLETED, outputs.backbone_pdbs / trajectory_pdbs populated. Save.

    -- normalised_contigs and copies are ORDINARY IN-MEMORY VARIABLES from here on (AD-5) --
    -- no file handoff between stages; this is the entire point of the single-job design --

11. Mark validate_state = RUNNING; save.

12. contigs_str = ":".join(normalised_contigs)            -- notebook line 503

    val_argv = ["/app/RFdiffusion/.venv/bin/python", "-m", "colabdesign.rf.designability_test",
                f"--pdb={run_dir}/{request.name}_0.pdb",
                f"--loc={run_dir}/{request.name}",
                f"--contig={contigs_str}",
                f"--copies={symmetry_plan.copies}",
                f"--num_seqs={request.num_seqs}",
                f"--num_recycles={request.num_recycles}",
                f"--rm_aa={request.rm_aa or ''}",
                f"--mpnn_sampling_temp={request.mpnn_sampling_temp}",
                f"--num_designs={request.num_designs}"]
    IF request.initial_guess:     val_argv.append("--initial_guess")
    IF request.use_multimer:      val_argv.append("--use_multimer")
    IF request.use_soluble_mpnn:  val_argv.append("--use_soluble")

13. result = ValidationExecutor.run(val_argv, cwd="/opt/weights/alphafold")   -- section 1.2, MANDATORY cwd

    IF result.exit_code != 0:
        mark validate_state = FAILED, error = result.stderr_tail; save. RETURN.

14. ResultPackager.package(run_dir, request.name)          -- zip; new artifact, no relocation needed

15. Mark validate_state = COMPLETED, outputs.best_pdb / best_design_pdb / result_zip populated.
    finished_at = now. Save.
```

**`--stage backbone`**: steps 1–10 only; `validate_state` explicitly set to `SKIPPED`.

**`--stage validate`**: load `RunRecord`, require `mode`/`normalised_contigs`/`copies` already present
(else fail immediately — "no completed backbone stage to validate against"), then run steps 11–15.
This is the retry path (FR-11) — it reads `normalised_contigs`/`copies` **from the saved `RunRecord`**
rather than from memory, since this is a fresh process invocation.

---

## 3. `InferenceExecutor` — Process Execution and Progress Polling

Transcribed from `run()` (notebook lines 144–225), adapted for `subprocess.Popen` instead of
`os.system` + raw PID tracking, and for `$TMPDIR` instead of `/dev/shm`.

```
run(argv, total_steps, num_designs, dump_dir, on_step) -> InferenceResult:
    clear any stale {n}.pdb in dump_dir for n in range(total_steps)   -- notebook lines 165-168

    proc = subprocess.Popen(argv, stdout=PIPE, stderr=PIPE, text=True)
        -- Popen gives a real handle: proc.poll() replaces the notebook's os.kill(pid, 0) liveness
           trick entirely; no PID-file dance needed.

    FOR design_i in range(num_designs):
        FOR step in range(total_steps):
            deadline = now() + STEP_TIMEOUT   -- see business-rules.md section 2 for the value and rationale
            LOOP:
                IF proc.poll() is not None:            -- process exited
                    IF f"{step}.pdb" exists and ends with "TER":
                        BREAK (treat as a fast final write)
                    ELSE:
                        RETURN InferenceResult(exit_code=proc.returncode, stderr_tail=last_4kb(stderr))
                IF f"{dump_dir}/{step}.pdb" exists and its content ends with "TER":
                    on_step(design_i, step, f"{dump_dir}/{step}.pdb")
                    delete f"{dump_dir}/{step}.pdb"
                    BREAK
                IF now() > deadline:
                    proc.terminate(); wait briefly; proc.kill() if still alive
                    RETURN InferenceResult(exit_code=STALL_EXIT_CODE, stderr_tail="step exceeded timeout")
                sleep(POLL_INTERVAL)   -- default 100ms, matches the notebook (line 179); configurable

    wait for proc to exit (num_designs * total_steps dumps all consumed; process should finish quickly)
    RETURN InferenceResult(exit_code=proc.returncode, stderr_tail=last_4kb(stderr))
```

**On `KeyboardInterrupt` / SIGTERM to the runner itself**: `proc.terminate()` the child, wait briefly,
`proc.kill()` if still alive, then re-raise — matches the notebook's `except KeyboardInterrupt:
os.kill(pid, SIGTERM)` (line 223), generalised to any signal the runner receives, since there is no
interactive kernel to interrupt inside a Slurm job.

---

## 4. `FramePublisher` and `ProgressReporter`

Already fully specified in Application Design (`component-methods.md` C-15/C-16) and Functional
Design DD-3/DD-6. Restated only where `InferenceExecutor`'s `on_step` hook binds them together:

- `ProgressReporter.update_step` is called **every step**, unconditionally — this is what keeps the
  progress bar smooth even when live preview is off.
- `FramePublisher.maybe_publish` is called **only if `request.live_preview`**, and only actually
  writes `current_frame.pdb` every `RFD_FRAME_EVERY_N` steps (default 5) within that.

---

## 5. `TemplateResolver`, `SymmetryDetector`, `ContigNormaliser`, `PdbPostProcessor`

These four map directly onto notebook logic already fully characterised in
`aidlc-docs/inception/reverse-engineering/`:

| Component | Notebook source | ColabDesign functions used |
|---|---|---|
| `TemplateResolver` | `get_pdb()`, lines 85–100 (Colab upload branch removed — replaced by a pre-uploaded file already in `run_dir`, staged by U4/U3 before the job was submitted) | — |
| `SymmetryDetector` | `run_ananas()`, lines 102–142 | `sym_it` |
| `ContigNormaliser` | inline in `run_diffusion()`, lines 271–309 | `fix_contigs`, `fix_partial_contigs` |
| `PdbPostProcessor` | lines 345–352 | `fix_pdb` |

No new behavioural decisions needed here beyond what reverse-engineering already documented — these
are direct transcriptions, using argument lists for `ananas` (NFR-11) instead of the notebook's
shell-string `os.system(cmd)`.

---

## 6. Traceability

| U2b component | Section | Verified against |
|---|---|---|
| `PipelineOrchestrator` | §2 | notebook lines 227–354, 478–517; `services.md` S-4 |
| `InferenceExecutor` | §3 | notebook lines 144–225 |
| Hydra config resolution | §1.1 | `run_inference.py` source at pinned SHA |
| AlphaFold `cwd` requirement | §1.2 | `colabdesign/af/alphafold/model/data.py`, `designability_test.py` at pinned SHA |
| `designability_test.py` invocation | §2 step 12 | `if __name__ == "__main__": main(sys.argv[1:])` confirmed present |
| G-13 satisfied by construction | §1.3 | notebook lines 234, 330 (the `output_prefix`/`dump_pdb_path` split already existed) |
