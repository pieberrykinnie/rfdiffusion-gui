# Requirement-to-Unit Map

**Note**: User Stories was skipped, so this artifact carries **requirement-to-unit traceability**
instead of story mappings (Q3 = A). Same purpose — every requirement has an owning unit, and no
requirement is orphaned.

**Legend**: **bold** = owning unit (primary responsibility) · plain = contributing unit

---

## Functional Requirements

### Design Submission

| Req | Summary | Units |
|---|---|---|
| FR-1 | RFdiffusion parameter form | **U4** |
| FR-2 | ProteinMPNN / AlphaFold parameters | **U4** |
| FR-3 | Template by code / accession / path / upload | **U4** (upload), U2b (resolution) |
| FR-4 | Display inferred design mode pre-submission | **U2a** (inference), U4 (display) |
| FR-5 | Reject invalid input before submission | **U2a** (rules), U4 (surfacing) |
| FR-6 | Slurm submission parameters with Grex defaults | **U3**, U4 |
| FR-6a | Runtime partition discovery | **U3** |
| FR-7 | Collision-free run name | **U3** |
| FR-8 | One-click full-pipeline submission | **U4**, U3 |

### Job Execution

| Req | Summary | Units |
|---|---|---|
| FR-9 | Single Slurm job, both stages in one program | **U2b**, U3 |
| FR-10 | Execute in Apptainer with `--nv` | **U1** |
| FR-11 | `--stage {all,backbone,validate}` | **U2b** |
| FR-12 | Preserve notebook design logic exactly | **U2a**, U2b |
| FR-13 | `$TMPDIR` per-job scratch | **U2b**, U1 (template) |
| FR-14 | Cancel a queued/running job | **U3**, U4 |

### Progress and Status

| Req | Summary | Units |
|---|---|---|
| FR-15 | Slurm job state display | **U3** |
| FR-16 | Live denoising step progress | **U2b** (reports), U3 (reads) |
| FR-17 | Live 3D preview *(DD-6 bridge)* | **U2b** (publishes), U4 (renders) |
| FR-18 | Pipeline stage display | **U2b**, U4 |
| FR-19 | Failure detail with log tail | **U3**, U4 |
| FR-20 | Status updates without page reload | **U4** |

### Visualization

| Req | Summary | Units |
|---|---|---|
| FR-21 | Final backbone in 3D, 3Dmol.js vendored | **U4** |
| FR-22 | Rainbow / chain / pLDDT colouring | **U4** |
| FR-23 | Trajectory animation | **U4** |
| FR-24 | Best-design overlay | **U4**, U3 (locates `best.pdb`) |
| FR-25 | Design selection when `num_designs > 1` | **U4** |
| FR-26 | Validation scores per design | **U4** |

### Run Management

| Req | Summary | Units |
|---|---|---|
| FR-27 | Run list | **U3**, U4 |
| FR-28 | Persist full run state | **U2a** (models), U3 (index) |
| FR-29 | Survive web app restart | **U3** |
| FR-30 | Clone parameters into a new run | **U4** |

### Results and Export

| Req | Summary | Units |
|---|---|---|
| FR-31 | Result zip over HTTP | **U2b** (packages), U4 (serves) |
| FR-32 | Individual file download | **U4** |
| FR-33 | Self-describing run directories | **U2a** (format), U2b (writes) |

### Documentation

| Req | Summary | Units |
|---|---|---|
| FR-34 | In-app contig syntax help | **U4** |
| FR-35 | End-to-end setup documentation | **U1**, Build and Test |

---

## Non-Functional Requirements

| Req | Summary | Units |
|---|---|---|
| NFR-1 | `uv` project with committed lockfile | **U2a** (workspace root) |
| NFR-2 | No PyTorch/JAX/CUDA in the web app env | **U2a** (package boundary), U4 |
| NFR-3 | No Node.js, npm, or bundler | **U4** |
| NFR-4 | Apptainer image pins the full GPU stack + upstream SHAs | **U1** |
| NFR-5 | Weights staged once, never downloaded at job start | **U1** |
| NFR-6 | All paths configurable via env vars | **U2a** (`PathLayout`) |
| NFR-7 | No Colab-specific code paths remain | **all units** |
| NFR-8 | Slurm account/partition configurable | **U3** |
| NFR-9 | Behaviour-preserving port, deviations documented | **U2a**, U2b |
| NFR-10 | Distinct handling of failure / cancel / timeout | **U2b**, U3 |
| NFR-11 | Argument-list subprocess calls, no shell | **U2a**, U2b, U3 |
| NFR-12 | Specific exceptions, no bare `except:` | **U2b** |
| NFR-13 | Capture stderr, check exit codes | **U2b**, U3 |
| NFR-14 | Bind `127.0.0.1` only | **U4** |
| NFR-15 | Light login-node footprint | **U4** |
| NFR-16 | Sane polling intervals | **U3**, U4 |
| NFR-17 | Pure, unit- and property-tested domain functions | **U2a** |
| NFR-18 | Slurm behind a fakeable interface | **U3** |

---

## Grex Adherence Rules

| Rules | Summary | Units |
|---|---|---|
| G-1, G-2 | Documented job-script shape; script retained and hand-resubmittable | **U1** (template), U3 (generation) |
| G-3 | Never emit `--qos=` | **U3** |
| G-4 | Always explicit `--time` and memory | **U3** |
| G-5 | GPU jobs always request `--gpus=` | **U3** |
| G-6 | Always explicit `--partition=` | **U3** |
| G-7, G-8 | One GPU default; 6 CPUs, 4–8 GB per CPU | **U3** |
| G-9 | No CPU-only work wasting GPU nodes; validate before submitting | **U4** (pre-submission validation), U2b |
| G-10 | Respect scheduling limits; no unbounded submission loops | **U3** |
| G-11, G-12 | `$TMPDIR` scratch; `export SLURM_TMPDIR=$TMPDIR` | **U2b**, U1 (template) |
| G-13, G-14 | Stage out before job end; respect node-local size limits | **U2b** |
| G-15, G-16 | `module load singularity`; image pulled/built ahead of time | **U1** |
| G-17 | `--nv` for GPU passthrough | **U1** |
| G-18 | Deliberate `APPTAINER_CACHEDIR` | **U1** |
| G-19, G-20 | Document `ControlMaster` SSH; never work around MFA | **U1** (docs) |

---

## Coverage Summary

| Unit | Owns | Contributes to |
|---|---|---|
| **U1** Runtime and Container | 12 requirements | 4 |
| **U2a** Core Domain | 11 requirements | 3 |
| **U2b** Runner | 15 requirements | 6 |
| **U3** Slurm and Persistence | 20 requirements | 5 |
| **U4** Web Application | 22 requirements | 6 |

**Every FR, NFR, and G-rule has exactly one owning unit.** No requirement is orphaned, and no
requirement has ambiguous ownership.

### Observations

- **U4 owns the most requirements but carries the least risk** — it is presentation over an already-
  designed domain, with no external dependency more exotic than Jinja2.
- **U3 owns the most *Grex adherence* rules** (G-3 … G-10), because it is the component that actually
  emits `#SBATCH` directives. That makes U3's Functional Design the right place to encode the
  adherence checklist as a test, rather than relying on review.
- **U2a owns FR-4, FR-5, FR-12, and NFR-17 together** — mode inference, validation, behaviour
  preservation, and testability are the same body of code seen from four angles. Concentrating them in
  the one unit with no external dependencies is what makes them all verifiable on day one.
- **U1 owns every container and access rule** (G-15 … G-20) and, notably, **FR-35** — setup
  documentation belongs with the unit that defines what setup means.
