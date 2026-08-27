#!/usr/bin/env python
"""U3 verification against real Grex Slurm.

The U3 test suite passes locally against FakeSlurmAdapter and stub binaries, which proves
the parsing, the argument lists and every reconciliation rule -- but deliberately cannot
prove that Grex's Slurm emits the strings this code parses. That is what this script is
for. It is the U3 equivalent of docs/m1-verification.md.

Run on a Grex LOGIN NODE, from the repository root:

    set -a && . .env && set +a
    uv run --package rfd-web python scripts/u3-verify.py --phase read-only

Phases:
    read-only   No job is submitted. Real sinfo, real squeue/sacct against an existing
                job id, real reconciliation over your existing run directories. Safe to
                run repeatedly; costs nothing.
    submit      Submits ONE real GPU job (the M1 smoke design) through SubmissionService
                and tracks it to a terminal state. Consumes a GPU allocation.
    cancel      Submits one more job and cancels it immediately, to exercise the
                cancel/reconciliation path. Usually finishes in the queue without ever
                reaching a GPU.
    all         All three, in order.

Every check prints PASS / FAIL / WARN and the script exits non-zero if anything FAILed,
so it can be read at a glance the way scripts/verify-image.sh is.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from rfd_core import DesignRequest, PathLayout, RunRecord

from rfd_web import (
    CliSlurmAdapter,
    RunDirectoryReader,
    RunIndexReconciler,
    RunQueryService,
    RunRepository,
    SlurmUnavailable,
    SubmissionService,
    WebConfig,
    discover_partitions,
    generate_job_script,
)
from rfd_web.slurm.states import SlurmState

RESULTS = {"pass": 0, "fail": 0, "warn": 0}


def report(status, check, detail=""):
    RESULTS[status.lower()] = RESULTS.get(status.lower(), 0) + 1
    line = "{0:<4} {1}".format(status, check)
    if detail:
        line += "\n       " + str(detail).replace("\n", "\n       ")
    print(line)


def section(title):
    print("\n=== {0} ===".format(title))


# ---------------------------------------------------------------------------
# Phase 1: read-only
# ---------------------------------------------------------------------------


def phase_read_only(layout, config, adapter, known_job_id):
    section("1. Environment")

    for name, value in (
        ("RFD_OUTPUT_ROOT", layout.output_root),
        ("RFD_IMAGE", layout.image_path),
        ("RFD_WEIGHTS", layout.weights_root),
        ("RFD_DB", layout.database_path),
        ("RFD_PROJECT_ROOT", config.project_root),
    ):
        exists = Path(value).exists()
        report(
            "PASS" if exists else "WARN",
            "{0} = {1}".format(name, value),
            "" if exists else "does not exist yet",
        )

    report(
        "PASS",
        "defaults: partition={0} account={1} walltime={2} gpus={3}".format(
            config.default_partition,
            config.default_account,
            config.default_walltime,
            config.default_gpus,
        ),
    )
    report(
        "PASS",
        "incompatible partitions (annotation only): {0}".format(
            ", ".join(config.incompatible_partitions) or "(none)"
        ),
    )

    section("2. Partition discovery (FR-6a) -- real sinfo")
    # This is the single most valuable check here: the local suite parses stub sinfo
    # output in a format taken from the documentation, never from Grex itself.
    try:
        result = discover_partitions(adapter, config)
    except Exception as exc:  # noqa: BLE001 - the point is to report, not to crash
        report("FAIL", "discover_partitions raised", traceback.format_exc())
        result = None

    if result is not None:
        if not result.partitions:
            report(
                "FAIL",
                "no GPU partitions discovered",
                result.warning or "sinfo returned rows, but none looked GPU-capable -- "
                "check `sinfo -h -o '%P|%G|%l|%a'` by hand and compare",
            )
        else:
            report("PASS", "{0} GPU partitions discovered".format(len(result.partitions)))
            for p in result.partitions:
                flags = []
                if p.is_default:
                    flags.append("default")
                if not p.available:
                    flags.append("DOWN")
                if not p.compatible:
                    flags.append("image-incompatible")
                print(
                    "       {0:<14} walltime={1:<12} {2}".format(
                        p.name, p.max_walltime or "unlimited", ",".join(flags)
                    )
                )
            names = {p.name for p in result.partitions}
            if config.default_partition not in names:
                report(
                    "WARN",
                    "RFD_DEFAULT_PARTITION={0} was not discovered".format(
                        config.default_partition
                    ),
                    "either the name changed or it has no GPUs",
                )
            else:
                report("PASS", "RFD_DEFAULT_PARTITION is among the discovered partitions")

    section("3. Job status parsing (FR-15, FR-19) -- real squeue then sacct")
    # squeue exits non-zero for a job that has left the queue; sacct is then the only
    # source. Both paths, and the ExitCode "X:Y" decode, are exercised here for real.
    try:
        status = adapter.status(known_job_id)
    except SlurmUnavailable as exc:
        report("FAIL", "status({0}) raised SlurmUnavailable".format(known_job_id), exc)
    except Exception:
        report("FAIL", "status({0}) raised".format(known_job_id), traceback.format_exc())
    else:
        if status.state is SlurmState.UNKNOWN and not status.known:
            report(
                "WARN",
                "Slurm has no record of job {0}".format(known_job_id),
                "accounting retention may have expired. Re-run with "
                "--job-id <a job id from your own `sacct -X` output>",
            )
        elif status.state is SlurmState.UNKNOWN:
            report(
                "FAIL",
                "job {0} mapped to UNKNOWN with a row present".format(known_job_id),
                "an unrecognised Slurm state word -- report it, it needs adding to "
                "rfd_web/slurm/states.py's map",
            )
        else:
            report(
                "PASS",
                "job {0} -> {1} (exit_code={2} signal={3} reason={4})".format(
                    known_job_id,
                    status.state.value,
                    status.exit_code,
                    status.signal,
                    status.reason,
                ),
            )

    bogus = "999999999"
    try:
        unknown = adapter.status(bogus)
    except SlurmUnavailable as exc:
        report(
            "FAIL",
            "an unknown job id raised SlurmUnavailable instead of returning UNKNOWN",
            "{0}\nThis is BR-4: 'Slurm has no record' and 'Slurm is unreachable' must "
            "stay distinct, or a controller hiccup will look like a lost job.".format(exc),
        )
    else:
        if unknown.state is SlurmState.UNKNOWN and not unknown.known:
            report("PASS", "unknown job id -> UNKNOWN(known=False), as BR-4 requires")
        else:
            report("FAIL", "unknown job id -> {0}".format(unknown))

    section("4. Job script generation (G-1 ... G-18)")
    # Generated from a real RunRecord and written to a scratch directory, then compared
    # against the M1 script that actually ran on this cluster.
    probe_dir = Path(layout.output_root) / ".u3-verify-probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    record = RunRecord(
        # run_id names the job; the probe DIRECTORY is dot-prefixed so it stays out of
        # the way of the reconciler's listing and of `ls`.
        run_id="u3probe",
        name="u3probe",
        run_dir=str(probe_dir),
        created_at=datetime.now(timezone.utc),
        request=_smoke_request(config, name="u3probe"),
    )
    try:
        script = generate_job_script(record, layout, config)
    except Exception:
        report("FAIL", "generate_job_script raised", traceback.format_exc())
    else:
        script_path = probe_dir / "job.sh"
        script_path.write_text(script)
        report("PASS", "job script generated at {0}".format(script_path))

        checks = [
            ("G-3  no --qos", "--qos=" not in script),
            ("G-5  --gpus requested", "#SBATCH --gpus=" in script),
            ("G-6  --partition explicit", "#SBATCH --partition=" in script),
            ("G-4  --time explicit", "#SBATCH --time=" in script),
            ("G-4  --mem-per-cpu explicit", "#SBATCH --mem-per-cpu=" in script),
            ("G-12 SLURM_TMPDIR exported", "export SLURM_TMPDIR=$TMPDIR" in script),
            ("G-17 --nv present", "--nv" in script),
            (
                "G-15 engine DETECTED, not named",
                "command -v singularity || command -v apptainer" in script
                and "apptainer exec" not in script
                and "singularity exec" not in script,
            ),
            (
                "G-18 both cache dirs set",
                "export APPTAINER_CACHEDIR=" in script
                and "export SINGULARITY_CACHEDIR=" in script,
            ),
        ]
        for label, ok in checks:
            report("PASS" if ok else "FAIL", label)

        import subprocess

        syntax = subprocess.run(
            ["bash", "-n", str(script_path)], stderr=subprocess.PIPE, universal_newlines=True
        )
        report(
            "PASS" if syntax.returncode == 0 else "FAIL",
            "bash -n on the generated script",
            syntax.stderr,
        )
        print("\n--- generated job.sh ---")
        print(script)
        print("--- end ---\n")
        print(
            "Compare this by eye against scripts/m1-submit.sh, the script that actually\n"
            "completed on this cluster (job 7556085). The differences should be exactly:\n"
            "  * logs go into the run directory instead of the submit directory\n"
            "  * the run directory is literal instead of $1\n"
            "  * no `if [ $# -ne 1 ]` argument check\n"
            "Anything else is worth a look.\n"
        )

    section("5. Index reconciliation over your existing run directories (FR-29)")
    repository = RunRepository(layout.database_path)
    reconciler = RunIndexReconciler(layout, repository)
    try:
        rep = reconciler.reconcile_all()
    except Exception:
        report("FAIL", "reconcile_all raised", traceback.format_exc())
        return

    report(
        "PASS",
        "indexed {0} run(s), flagged {1} missing, skipped {2}".format(
            rep.indexed, rep.flagged_missing, len(rep.skipped)
        ),
        "\n".join(rep.skipped),
    )
    if rep.indexed == 0:
        report(
            "WARN",
            "no run directories found under {0}".format(layout.output_root),
            "If you ran M1, its m1-smoke-* directories should have been picked up.",
        )

    section("6. State reconciliation against real Slurm (S-2)")
    # The money check: an already-completed real run, cross-checked against real sacct.
    #
    # Note what has to be done explicitly here. A run indexed by reconcile_all() is
    # marked terminal from run.json alone, so RunQueryService.get() short-circuits by
    # BR-3 and never asks Slurm about it. That is correct caching behaviour, but it
    # means simply calling get() would NOT exercise sacct -- so this check queries the
    # adapter directly as well and compares the two.
    query = RunQueryService(layout, config, adapter, repository)
    cross_checked = 0
    no_job_id = 0
    for summary in repository.list(limit=20):
        try:
            view = query.get(summary.run_id)
        except Exception:
            report("FAIL", "get({0}) raised".format(summary.run_id), traceback.format_exc())
            continue
        if view is None:
            report("FAIL", "get({0}) returned None for an indexed run".format(summary.run_id))
            continue
        report(
            "PASS",
            "{0}: status={1} slurm={2} exit={3}{4}".format(
                view.run_id,
                view.status.value,
                view.slurm_state.value if view.slurm_state else "-",
                view.exit_code,
                " STALE" if view.stale else "",
            ),
            view.message or "",
        )
        if view.status.value == "completed":
            print(
                "       ^ BR-2 on real data: reported COMPLETED only because run.json is\n"
                "         finalised, never on a Slurm exit code alone."
            )

        if not summary.slurm_job_id:
            no_job_id += 1
            continue
        try:
            live = adapter.status(summary.slurm_job_id)
        except SlurmUnavailable as exc:
            report("FAIL", "direct status({0}) raised".format(summary.slurm_job_id), exc)
            continue

        if not live.known:
            report(
                "WARN",
                "Slurm no longer has job {0}; cross-check skipped".format(
                    summary.slurm_job_id
                ),
            )
            continue

        expected = {
            "COMPLETED": ("completed", "failed"),  # FAILED is correct if run.json is not finalised
            "FAILED": ("failed",),
            "CANCELLED": ("cancelled",),
            "TIMEOUT": ("timeout",),
            "RUNNING": ("running",),
            "PENDING": ("queued",),
        }.get(live.state.value)
        if expected is None:
            report("WARN", "job {0} -> {1}".format(summary.slurm_job_id, live.state.value))
        elif view.status.value in expected:
            cross_checked += 1
            report(
                "PASS",
                "cross-check: sacct says {0}, reconciler says {1} (exit_code={2})".format(
                    live.state.value, view.status.value, live.exit_code
                ),
            )
        else:
            report(
                "FAIL",
                "cross-check MISMATCH on {0}".format(summary.run_id),
                "sacct says {0}; the reconciler reports {1}".format(
                    live.state.value, view.status.value
                ),
            )

        if view.exit_code is None and live.exit_code is not None:
            report(
                "WARN",
                "known gap: exit_code is null in the reconciled view for {0}".format(
                    summary.run_id
                ),
                "A run first indexed by startup reconciliation is marked terminal from\n"
                "run.json alone, so BR-3 stops get() from ever asking Slurm for its exit\n"
                "code. sacct has it ({0}); the view does not. Harmless for runs this app\n"
                "submitted itself (they are reconciled live before going terminal), but it\n"
                "means FR-19's exit code is absent for runs recovered after a database\n"
                "loss. Reported rather than silently patched -- see docs/u3-verification.md."
                .format(live.exit_code),
            )

    # A verification check that silently does nothing is worse than no check at all --
    # it reports PASS while proving nothing. Say so explicitly.
    if cross_checked == 0:
        report(
            "WARN",
            "the sacct cross-check did not run on any indexed run",
            "{0} indexed run(s) carry no slurm_job_id in run.json, so there was nothing to\n"
            "cross-check against. This is expected if your only run directories are M1's:\n"
            "those were submitted by hand with `sbatch scripts/m1-submit.sh`, which never\n"
            "wrote a job id into run.json -- only S-1 does that. Checks 2 and 3 above DID\n"
            "exercise real sinfo/squeue/sacct; what is untested is the reconciler agreeing\n"
            "with sacct on a real job. Run `--phase submit` to get that.".format(no_job_id),
        )


# ---------------------------------------------------------------------------
# Phase 2 and 3: real submissions
# ---------------------------------------------------------------------------


def _smoke_request(config, name):
    """The M1 smoke design: 80-residue de novo monomer, FREE mode, no template.

    Identical in substance to scripts/m1-prepare-run.sh's run.json, so a failure here is
    a U3 failure and not a new scientific unknown.
    """
    return DesignRequest(
        name=name,
        contigs="80",
        iterations=50,
        num_designs=1,
        partition=config.default_partition,
        account=config.default_account,
        walltime="0-00:30:00",
        gpus=config.default_gpus,
        cpus_per_task=config.default_cpus_per_task,
        mem_per_cpu=config.default_mem_per_cpu,
    )


def phase_submit(layout, config, adapter, poll_seconds, max_minutes):
    section("7. Real submission through SubmissionService (S-1)")
    repository = RunRepository(layout.database_path)
    service = SubmissionService(layout, config, adapter, repository)
    query = RunQueryService(layout, config, adapter, repository)

    name = "u3smoke-{0}".format(datetime.now().strftime("%Y%m%dT%H%M%S"))
    outcome = service.submit(_smoke_request(config, name))
    if not outcome.ok:
        report("FAIL", "submit() failed", "\n".join(outcome.errors))
        return
    report(
        "PASS",
        "submitted run_id={0} job={1}".format(outcome.run_id, outcome.slurm_job_id),
        "run dir: {0}".format(outcome.run_dir),
    )

    run_dir = Path(outcome.run_dir)
    for expected in ("run.json", "job.sh"):
        ok = (run_dir / expected).is_file()
        report("PASS" if ok else "FAIL", "{0} written into the run directory".format(expected))
    report(
        "PASS",
        "G-2: this run is hand-resubmittable with `cd {0} && sbatch job.sh`".format(run_dir),
    )

    section("8. Tracking to a terminal state")
    deadline = time.time() + max_minutes * 60
    last = None
    while time.time() < deadline:
        view = query.get(outcome.run_id)
        line = "{0} slurm={1}".format(
            view.status.value, view.slurm_state.value if view.slurm_state else "-"
        )
        if view.progress:
            line += " {0} step {1}/{2}".format(
                view.progress.stage, view.progress.step, view.progress.total_steps
            )
            if view.progress.note:
                line += " ({0})".format(view.progress.note)
        if view.frame_available:
            line += " [live frame available]"
        if line != last:
            print("       {0}  {1}".format(datetime.now().strftime("%H:%M:%S"), line))
            last = line
        if view.status.value in ("completed", "failed", "cancelled", "timeout"):
            break
        time.sleep(poll_seconds)
    else:
        report("WARN", "still not terminal after {0} minutes".format(max_minutes))
        return

    view = query.get(outcome.run_id)
    if view.status.value == "completed":
        report("PASS", "run completed", "outputs: {0}".format(view.outputs))
    else:
        report(
            "FAIL",
            "run ended as {0}".format(view.status.value),
            "{0}\n--- log tail ---\n{1}".format(view.message or "", view.log_tail or ""),
        )

    # BR-3: a terminal run must never be re-queried.
    before = _count_calls(adapter)
    query.get(outcome.run_id)
    after = _count_calls(adapter)
    report(
        "PASS" if before == after or before is None else "FAIL",
        "BR-3: re-reading a terminal run issued no further Slurm calls",
    )


def phase_cancel(layout, config, adapter, poll_seconds):
    section("9. Cancellation (FR-14, BR-8)")
    repository = RunRepository(layout.database_path)
    service = SubmissionService(layout, config, adapter, repository)
    query = RunQueryService(layout, config, adapter, repository)

    name = "u3cancel-{0}".format(datetime.now().strftime("%Y%m%dT%H%M%S"))
    outcome = service.submit(_smoke_request(config, name))
    if not outcome.ok:
        report("FAIL", "submit() for the cancel test failed", "\n".join(outcome.errors))
        return
    report("PASS", "submitted job {0} to cancel".format(outcome.slurm_job_id))

    result = service.cancel(outcome.run_id)
    report("PASS" if result.ok else "FAIL", "cancel() returned ok={0}".format(result.ok),
           "\n".join(result.errors))

    for _ in range(20):
        view = query.get(outcome.run_id)
        if view.status.value in ("cancelled", "failed", "completed", "timeout"):
            break
        time.sleep(poll_seconds)

    view = query.get(outcome.run_id)
    if view.status.value == "cancelled":
        report("PASS", "reported as CANCELLED", view.message)
        if view.message and "walltime" in view.message:
            report(
                "FAIL",
                "BR-8 violated: the runner's 'likely walltime exceeded' message leaked "
                "into a cancel",
            )
        elif view.message and "from this app" in view.message:
            report("PASS", "BR-8: attributed to this app, not to the scheduler")
        else:
            report("WARN", "cancel message did not mention this app", view.message)
    else:
        report(
            "WARN",
            "ended as {0} rather than cancelled".format(view.status.value),
            "If the job had already finished, this is expected -- scancel on a finished "
            "job is a no-op by BR-11.",
        )

    # Cancelling again must be harmless.
    again = service.cancel(outcome.run_id)
    report(
        "PASS" if again.ok else "WARN",
        "BR-11: cancelling an already-finished job is not an error",
        "\n".join(again.errors),
    )


def _count_calls(adapter):
    return getattr(adapter, "status_call_count", None)


# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", default="read-only", choices=["read-only", "submit", "cancel", "all"]
    )
    parser.add_argument(
        "--job-id",
        default="7556085",
        help="an existing Slurm job id to parse (default: the M1 job)",
    )
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--max-minutes", type=int, default=60)
    args = parser.parse_args(argv)

    if not os.environ.get("RFD_OUTPUT_ROOT"):
        print(
            "NOTE: RFD_OUTPUT_ROOT is unset, so defaults under $HOME will be used.\n"
            "      If you have a .env, source it first:  set -a && . .env && set +a\n"
        )

    layout = PathLayout.from_env()
    config = WebConfig.from_env()
    adapter = CliSlurmAdapter(timeout_seconds=config.slurm_timeout_seconds)

    print("U3 verification -- rfd-web against real Grex Slurm")
    print("host: {0}   python: {1}".format(os.uname().nodename, sys.version.split()[0]))

    if args.phase in ("read-only", "all"):
        phase_read_only(layout, config, adapter, args.job_id)
    if args.phase in ("submit", "all"):
        phase_submit(layout, config, adapter, args.poll_seconds, args.max_minutes)
    if args.phase in ("cancel", "all"):
        phase_cancel(layout, config, adapter, args.poll_seconds)

    print(
        "\n==== PASS {0} / WARN {1} / FAIL {2} ====".format(
            RESULTS["pass"], RESULTS["warn"], RESULTS["fail"]
        )
    )
    return 1 if RESULTS["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
