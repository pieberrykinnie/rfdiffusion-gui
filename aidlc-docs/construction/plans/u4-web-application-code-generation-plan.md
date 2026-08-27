# U4 Web Application — Code Generation Plan

**Unit**: U4 Web Application
**Package**: `packages/rfd-web/src/rfd_web/` (brownfield — U3 already exists)
**Date**: 2026-08-27
**Status**: AWAITING APPROVAL

This plan is the **single source of truth** for U4 Code Generation. No code is generated
outside this plan; no step is skipped or reordered.

---

## Unit Context

### What already exists (U3)
`packages/rfd-web/src/rfd_web/` contains 18 source modules across `slurm/`, `persistence/`,
`services/`, plus `config.py`, `errors.py`, `status.py`, and `__init__.py`. **225 tests,
96% coverage.** These modules provide:
- `SubmissionService` (S-1): submit, resubmit, cancel
- `RunQueryService` (S-2): get (reconciled), list_runs (index-only)
- `RunDirectoryReader`: resolve_within (path containment), read_record, read_progress,
  current_frame, list_designs, best_design_index, log_tail
- `PartitionCache` → `DiscoveryResult` with warning + incompatible annotations
- `FakeSlurmAdapter`: importable from src, not tests — full app runs offline
- `RunIndexReconciler`: startup reconciliation from run directories
- `WebConfig`: all env-var defaults parsed

### What U4 adds
- **FastAPI application factory** with Jinja2, HTMX, and static file serving
- **16 route endpoints** (C-28) across run lifecycle, visualization, and management
- **C-26 RequestValidator** route-layer glue (core `validate()` already exists in `rfd-core`)
- **C-27 TemplateUploadHandler** — browser file upload for template PDBs
- **S-3 ResultService** — locate and serve run artifacts (zip, PDB, trajectory, files)
- **7 Jinja2 templates** — base layout, run list, new-run form, run detail, contig help,
  error page, HTMX status fragment
- **Static assets** — vendored 3Dmol.js, CSS, JS for viewer interaction
- **App entry point** (`__main__.py`) — uvicorn with `127.0.0.1` binding

### Dependencies
- `rfd-core`: `DesignRequest`, `validate()`, `preview_mode()`, `PathLayout`, `RunRecord`,
  `DesignMode`, `SymmetryKind`, `StageState`, `get_Ls()`
- `rfd-web` (U3): `SubmissionService`, `RunQueryService`, `RunView`, `ProgressView`,
  `PartitionCache`, `DiscoveryResult`, `RunDirectoryReader`, `RunIndexReconciler`,
  `WebConfig`, `FakeSlurmAdapter`, all error types
- **Never** `rfd-runner` (DD-1, NFR-2)

### Constraints
- **Python 3.9** — `Optional[X]` not `X | None`, no `StrEnum`, no `match`
- **No Node.js/npm/bundler** (NFR-3) — all static assets vendored
- **Bind `127.0.0.1` only** (NFR-14)
- **`data-testid` on all interactive elements** (code-generation.md automation rules)
- **`ananas` may be unavailable** — symmetry selector must detect and degrade

### Story Traceability
| Step | Requirements covered |
|---|---|
| 1 | (setup) |
| 2 | NFR-3 (vendored assets) |
| 3 | NFR-14, NFR-15 |
| 4 | FR-5, FR-4 |
| 5 | FR-3 |
| 6 | FR-31, FR-32, FR-21, FR-23, FR-24 |
| 7 | FR-27 |
| 8 | FR-1, FR-2, FR-4, FR-6 |
| 9 | FR-8, FR-5 |
| 10 | FR-15, FR-18, FR-16, FR-17, FR-19, FR-20 |
| 11 | FR-14, FR-30 |
| 12 | FR-21, FR-23, FR-24, FR-31, FR-32 |
| 13 | FR-34 |
| 14 | FR-22, FR-23, FR-24, FR-25 |
| 15 | FR-27 |
| 16 | FR-1, FR-2, FR-4, FR-6 |
| 17 | FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-26 |
| 18 | FR-34 |
| 19 | NFR-3 |
| 20 | NFR-14, NFR-15 |
| 21-23 | (testing) |
| 24 | (documentation) |
| 25 | (config) |

---

## Step 1: Project Setup — Add HTTP Dependencies to `rfd-web`
- [ ] Add `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart` to
      `packages/rfd-web/pyproject.toml` dependencies
- [ ] Add `httpx` to dev dependencies (for `TestClient`)
- [ ] Run `uv lock` to verify resolution succeeds on Python 3.9
- [ ] Verify no `rfd-runner` dependency introduced

**Files modified**: `packages/rfd-web/pyproject.toml`, `uv.lock`

---

## Step 2: Vendor 3Dmol.js
- [ ] Download `3Dmol-min.js` (latest stable release) to
      `packages/rfd-web/src/rfd_web/static/vendor/3Dmol-min.js`
- [ ] Record version and source URL in a `LICENSE-3Dmol.txt` alongside
- [ ] Verify the file is self-contained (no external fetches at runtime)

**Files created**: `static/vendor/3Dmol-min.js`, `static/vendor/LICENSE-3Dmol.txt`
**Requirements**: FR-21 (vendored locally), NFR-3 (no CDN)

---

## Step 3: Application Factory — `app.py`
- [ ] Create `packages/rfd-web/src/rfd_web/app.py`
- [ ] `create_app(config: WebConfig, slurm: SlurmAdapter, layout: PathLayout) -> FastAPI`
- [ ] Mount static files at `/static` from the `static/` directory
- [ ] Configure Jinja2 templates from the `templates/` directory
- [ ] Wire startup: `RunIndexReconciler.reconcile_all()`, `PartitionCache` init
- [ ] Store services (`SubmissionService`, `RunQueryService`, `ResultService`,
      `PartitionCache`, `RunDirectoryReader`, `WebConfig`, `PathLayout`) on `app.state`
- [ ] Include all route routers
- [ ] Never bind to `0.0.0.0` — enforce `127.0.0.1` in the factory's defaults

**Files created**: `app.py`
**Requirements**: NFR-14 (localhost only), NFR-15 (light footprint)

---

## Step 4: Request Validation Glue — `validation.py` (route-layer)
- [ ] Create `packages/rfd-web/src/rfd_web/validation.py`
- [ ] `parse_form_to_request(form_data: dict, config: WebConfig) -> DesignRequest`
  — converts HTML form values (strings) to typed `DesignRequest` fields with sensible
  defaults from `WebConfig`
- [ ] `format_validation_errors(outcome: ValidationOutcome) -> list[str]`
  — renders errors for template display
- [ ] Reuse `rfd_core.validate()` and `rfd_core.preview_mode()` — no duplicate logic

**Files created**: `validation.py`
**Requirements**: FR-5 (clear errors), FR-4 (preview mode)

---

## Step 5: Template Upload Handler — `upload.py` (C-27)
- [ ] Create `packages/rfd-web/src/rfd_web/upload.py`
- [ ] `async save_upload(upload: UploadFile, run_dir: Path) -> Path`
- [ ] Validate file extension (`.pdb` only), size limit (configurable, default 50 MB)
- [ ] Write to `run_dir/template.pdb` atomically (temp + rename)
- [ ] Return the path for `SubmissionService.submit(template_path=...)`

**Files created**: `upload.py`
**Requirements**: FR-3 (browser upload replaces `google.colab.files.upload()`)

---

## Step 6: Result Service — `services/result.py` (S-3)
- [ ] Create `packages/rfd-web/src/rfd_web/services/result.py`
- [ ] `class ResultService`
- [ ] `get_result_zip(run_id: str) -> Optional[Path]` — locates `{name}.result.zip`
- [ ] `get_structure(run_id: str, design_index: int) -> Optional[Path]` — backbone PDB
- [ ] `get_trajectory(run_id: str, design_index: int) -> Optional[Path]` — traj PDB
- [ ] `get_best_overlay(run_id: str) -> Optional[dict]` — best-design PDB path + index
- [ ] `get_file(run_id: str, relative_path: str) -> Optional[Path]` — uses
      `RunDirectoryReader.resolve_within()` for path containment (BR-14)
- [ ] All methods: return `None` when artifact doesn't exist (routes return 404)

**Files created**: `services/result.py`
**Requirements**: FR-31 (zip), FR-32 (individual file), FR-21 (backbone), FR-23 (trajectory),
FR-24 (best overlay)

---

## Step 7: Routes — Run List — `routes/runs.py` (partial)
- [ ] Create `packages/rfd-web/src/rfd_web/routes/__init__.py`
- [ ] Create `packages/rfd-web/src/rfd_web/routes/runs.py`
- [ ] `GET /` — calls `RunQueryService.list_runs()`, renders `run_list.html`
- [ ] Sort by `created_at` descending (newest first)
- [ ] Show: name, status badge, created time, mode, partition

**Files created**: `routes/__init__.py`, `routes/runs.py`
**Requirements**: FR-27 (run list)

---

## Step 8: Routes — New Run Form — `routes/submit.py`
- [ ] Create `packages/rfd-web/src/rfd_web/routes/submit.py`
- [ ] `GET /new` — renders `new_run.html` with:
  - All 20 scientific parameters as form fields (DD-7)
  - Slurm parameters (partition, account, walltime, gpus, cpus_per_task, mem_per_cpu)
  - Partition dropdown from `PartitionCache.get()` with incompatible annotations
  - Template file upload field
  - Symmetry selector that detects `ananas` availability and disables `auto` if absent
  - Live mode preview via HTMX `POST /api/preview-mode` on contigs field change
  - Defaults from `WebConfig`
- [ ] `POST /api/preview-mode` — calls `rfd_core.preview_mode(contigs)`, returns HTMX
      fragment showing inferred `DesignMode`

**Files created**: `routes/submit.py`
**Requirements**: FR-1 (web form), FR-2 (all parameters), FR-4 (live mode preview),
FR-6 (partition discovery)

---

## Step 9: Routes — Run Submission — `routes/submit.py` (continued)
- [ ] `POST /runs` in `routes/submit.py`:
  1. Parse form data → `DesignRequest` via `parse_form_to_request()`
  2. Handle template upload via `save_upload()` if file provided
  3. Validate via `rfd_core.validate(request)`
  4. If errors: re-render form with errors (no redirect)
  5. If ok: call `SubmissionService.submit(request, template_path)`
  6. Redirect to `GET /runs/{id}` on success

**Files modified**: `routes/submit.py`
**Requirements**: FR-8 (one-click submit), FR-5 (validation errors)

---

## Step 10: Routes — Run Detail and Status Polling — `routes/detail.py`
- [ ] Create `packages/rfd-web/src/rfd_web/routes/detail.py`
- [ ] `GET /runs/{id}` — calls `RunQueryService.get()`, renders `run_detail.html`:
  - Status badge with Slurm state
  - Pipeline stage progress (backbone/validate) (FR-18)
  - Live denoising step progress bar (FR-16) — from `ProgressView`
  - 3Dmol.js live preview container (FR-17) — loads from `/runs/{id}/frame`
  - Failure info: error message + log tail (FR-19)
  - Stale-progress note for validate stage (BR-5)
  - Frame availability from `current_frame.pdb`, not `progress.json` (BR-6)
- [ ] `GET /runs/{id}/status` — HTMX partial, returns only the status fragment
  - Polled by HTMX at `RFD_STATUS_POLL_SECONDS` interval (FR-20, NFR-16)
  - Stops polling when status is terminal
- [ ] `GET /runs/{id}/frame` — returns `current_frame.pdb` content if available,
      404 otherwise

**Files created**: `routes/detail.py`
**Requirements**: FR-15, FR-16, FR-17, FR-18, FR-19, FR-20

---

## Step 11: Routes — Cancel and Clone — `routes/detail.py` (continued)
- [ ] `POST /runs/{id}/cancel` — calls `SubmissionService.cancel()`, redirects back
- [ ] `POST /runs/{id}/clone` — reads `RunView`, populates form fields, redirects to
      `GET /new?clone_from={id}` with query params

**Files modified**: `routes/detail.py`
**Requirements**: FR-14 (cancel), FR-30 (clone params)

---

## Step 12: Routes — File Serving — `routes/files.py`
- [ ] Create `packages/rfd-web/src/rfd_web/routes/files.py`
- [ ] `GET /runs/{id}/structure/{n}` — backbone PDB via `ResultService.get_structure()`
- [ ] `GET /runs/{id}/trajectory/{n}` — trajectory PDB via `ResultService.get_trajectory()`
- [ ] `GET /runs/{id}/best` — best overlay data via `ResultService.get_best_overlay()`
- [ ] `GET /runs/{id}/download` — result zip via `ResultService.get_result_zip()`,
      served as `FileResponse` with `Content-Disposition: attachment`
- [ ] `GET /runs/{id}/file/{path:path}` — individual file via `ResultService.get_file()`,
      uses `resolve_within()` for path containment (BR-14)
- [ ] All endpoints: return 404 if artifact not found

**Files created**: `routes/files.py`
**Requirements**: FR-21, FR-23, FR-24, FR-31, FR-32

---

## Step 13: Routes — Help — `routes/help.py`
- [ ] Create `packages/rfd-web/src/rfd_web/routes/help.py`
- [ ] `GET /help/contigs` — renders `contig_help.html` with:
  - Contig syntax explanation
  - The notebook's original worked examples (from `reference/diffusion.py`)
  - Examples for each `DesignMode` (free, fixed, partial)

**Files created**: `routes/help.py`
**Requirements**: FR-34 (in-app help)

---

## Step 14: Static Assets — CSS and Viewer JS
- [ ] Create `packages/rfd-web/src/rfd_web/static/css/style.css`
  - Dark-mode theme (modern, scientific tool aesthetic)
  - Status badge colours (queued=blue, running=amber, completed=green, failed=red,
    cancelled=grey, timeout=orange)
  - Form layout, card components, progress bar styling
  - Responsive layout for the run detail page (viewer panel + info panel)
- [ ] Create `packages/rfd-web/src/rfd_web/static/js/viewer.js`
  - Initialize 3Dmol.js viewer in the detail page container
  - `loadFrame(url)` — fetches PDB from `/runs/{id}/frame`, displays with rainbow colouring
  - `loadStructure(url, colorScheme)` — loads final backbone with selectable colouring:
    rainbow (FR-22a), chain (FR-22b), pLDDT B-factor (FR-22c)
  - `loadTrajectory(url)` — loads trajectory PDB, frame-by-frame animation (FR-23)
  - `loadBestOverlay(url)` — loads best-design + backbone overlay (FR-24)
  - Design selector for `num_designs > 1` (FR-25)
  - Colour scheme selector dropdown
  - Auto-refresh live frame during RUNNING status via polling

**Files created**: `static/css/style.css`, `static/js/viewer.js`
**Requirements**: FR-22, FR-23, FR-24, FR-25

---

## Step 15: Template — Base Layout — `templates/base.html`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/base.html`
- [ ] HTML5 semantic structure with `<meta charset="utf-8">`
- [ ] Include vendored 3Dmol.js script tag
- [ ] Include `style.css` and `viewer.js` links
- [ ] Include HTMX via vendored copy or inline (no CDN — NFR-3)
- [ ] Navigation bar: "RFdiffusion GUI" title, "New Run" link, "Run List" link
- [ ] Content block for child templates
- [ ] Footer with status info

**Files created**: `templates/base.html`
**Requirements**: NFR-3 (no CDN)

---

## Step 16: Template — New Run Form — `templates/new_run.html`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/new_run.html`
- [ ] Extends `base.html`
- [ ] Organized form sections:
  - **Design Parameters**: name, contigs (with link to `/help/contigs`), template upload,
    iterations, hotspot, num_designs
  - **Mode Preview**: HTMX-driven display of inferred mode (updates on contigs change)
  - **Symmetry**: kind selector (none/auto/cyclic/dihedral), order field (shown when
    cyclic/dihedral), `auto` disabled with note if `ananas` unavailable
  - **Advanced**: chains, add_potential, partial_T, use_beta_model, live_preview
  - **Validation (ProteinMPNN/AlphaFold)**: num_seqs, mpnn_sampling_temp, rm_aa,
    use_soluble_mpnn, initial_guess, num_recycles, use_multimer
  - **Slurm**: partition (dropdown with incompatible annotations), account, walltime,
    gpus, cpus_per_task, mem_per_cpu
- [ ] Pre-fill from `WebConfig` defaults; pre-fill from clone data if `?clone_from=`
- [ ] Error display area for validation errors
- [ ] Submit button "Launch Run"
- [ ] `data-testid` on all interactive elements

**Files created**: `templates/new_run.html`
**Requirements**: FR-1, FR-2, FR-4, FR-6

---

## Step 17: Template — Run Detail — `templates/run_detail.html`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/run_detail.html`
- [ ] Extends `base.html`
- [ ] Header: run name, status badge, created time
- [ ] **Status section** (HTMX target, polled at `status_poll_seconds`):
  - Slurm job ID and state
  - Pipeline stage: backbone / validate with individual state badges
  - Progress bar (step X of Y) for backbone stage
  - Note for validate stage: "validating (no step-level progress available)" when stale (BR-5)
  - Cancel button (shown when not terminal)
- [ ] **3Dmol.js Viewer** (right panel on desktop):
  - Live frame preview during RUNNING (auto-refreshes)
  - Final structure viewer when COMPLETED:
    - Design selector (dropdown for `num_designs > 1`)
    - Colour scheme selector (rainbow / chain / pLDDT)
    - Trajectory animation controls (play/pause/step)
    - Best-design overlay toggle
  - Validation scores per design (FR-26)
- [ ] **Error section** (shown when FAILED/TIMEOUT):
  - Error message from `RunView.message`
  - Log tail in a collapsible `<pre>` block (FR-19)
  - Exit code
- [ ] **Results section** (shown when COMPLETED):
  - Download zip button
  - File list with individual download links
  - Clone parameters button
- [ ] `data-testid` on all interactive elements

**Files created**: `templates/run_detail.html`
**Requirements**: FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-26

---

## Step 18: Template — Run List — `templates/run_list.html`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/run_list.html`
- [ ] Extends `base.html`
- [ ] Table/card list of runs from `RunQueryService.list_runs()`
- [ ] Columns: name (linked to detail), status badge, mode, partition, created time
- [ ] "New Run" button at the top
- [ ] Empty state message when no runs exist

**Files created**: `templates/run_list.html`
**Requirements**: FR-27

---

## Step 19: Template — Contig Help — `templates/contig_help.html`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/contig_help.html`
- [ ] Extends `base.html`
- [ ] Contig syntax reference with:
  - Format description (chains separated by `/`, segments by space)
  - Fixed segment syntax (`A163-181`)
  - Free segment syntax (`10-40`)
  - Mode inference rules (all free → FREE, all fixed → FIXED, mixed → PARTIAL)
  - Worked examples from the original notebook (`reference/diffusion.py`)

**Files created**: `templates/contig_help.html`
**Requirements**: FR-34

---

## Step 20: Template — Status Fragment + Error — `templates/fragments/`
- [ ] Create `packages/rfd-web/src/rfd_web/templates/fragments/status.html`
  - HTMX partial for `GET /runs/{id}/status`
  - Contains the status badge, progress bar, stage info, cancel button
  - Includes `hx-get` for self-polling (stops when terminal)
- [ ] Create `packages/rfd-web/src/rfd_web/templates/error.html`
  - Generic error page (404, 500)

**Files created**: `templates/fragments/status.html`, `templates/error.html`
**Requirements**: FR-20 (HTMX polling)

---

## Step 21: App Entry Point — `__main__.py`
- [ ] Create `packages/rfd-web/src/rfd_web/__main__.py`
- [ ] Parse `RFD_BIND_HOST` (default `127.0.0.1`) and `RFD_BIND_PORT` (default `8080`)
- [ ] Determine Slurm adapter: `CliSlurmAdapter` if `sinfo` on PATH, else `FakeSlurmAdapter`
      with a startup warning
- [ ] Create `PathLayout.from_env()`, `WebConfig.from_env()`
- [ ] Call `create_app(config, slurm, layout)` and `uvicorn.run()`
- [ ] Print startup banner with URL and adapter type

**Files created**: `__main__.py`
**Requirements**: NFR-14, NFR-15

---

## Step 22: Vendor HTMX
- [ ] Download `htmx.min.js` (latest stable) to
      `packages/rfd-web/src/rfd_web/static/vendor/htmx.min.js`
- [ ] Record version and source URL in `LICENSE-htmx.txt`

**Files created**: `static/vendor/htmx.min.js`, `static/vendor/LICENSE-htmx.txt`
**Requirements**: NFR-3 (no CDN)

---

## Step 23: Update `__init__.py` Exports
- [ ] Add new public exports to `packages/rfd-web/src/rfd_web/__init__.py`:
  `create_app`, `ResultService`, `parse_form_to_request`, `save_upload`
- [ ] Keep all existing U3 exports unchanged

**Files modified**: `__init__.py`

---

## Step 24: Test Suite — Route and Integration Tests
- [ ] Create `packages/rfd-web/tests/test_app.py` — app factory tests
- [ ] Create `packages/rfd-web/tests/test_routes_list.py` — `GET /` tests
- [ ] Create `packages/rfd-web/tests/test_routes_submit.py` — `GET /new`, `POST /runs`,
      `POST /api/preview-mode` tests
- [ ] Create `packages/rfd-web/tests/test_routes_detail.py` — `GET /runs/{id}`,
      `GET /runs/{id}/status`, `POST /runs/{id}/cancel`, `POST /runs/{id}/clone`
- [ ] Create `packages/rfd-web/tests/test_routes_files.py` — all file-serving endpoints
- [ ] Create `packages/rfd-web/tests/test_routes_help.py` — `GET /help/contigs`
- [ ] Create `packages/rfd-web/tests/test_upload.py` — `save_upload()` unit tests
- [ ] Create `packages/rfd-web/tests/test_result_service.py` — `ResultService` unit tests
- [ ] Create `packages/rfd-web/tests/test_validation_glue.py` — `parse_form_to_request()`
- [ ] All tests use `FakeSlurmAdapter` and `TestClient` (httpx)
- [ ] All tests use `tmp_path` fixtures for run directories and SQLite
- [ ] Target: all new code covered; existing U3 tests unchanged and still passing
- [ ] Run full suite: `uv run --package rfd-web pytest` — expect ≥ 300 tests, ≥ 90% coverage
- [ ] Run workspace suite: `uv run pytest` — expect all packages pass (456+ existing + new)

**Files created**: 9 test files
**Requirements**: (testing coverage)

---

## Step 25: Documentation and Config Updates
- [ ] Create `aidlc-docs/construction/u4-web-application/code/u4-code-summary.md`
  - Files created vs modified
  - Test count and coverage
  - Requirement coverage matrix
  - Known limitations
- [ ] Update `env.example` with any new env vars (if any beyond `RFD_BIND_HOST`/`RFD_BIND_PORT`
      already present)
- [ ] Update `packages/rfd-web/README.md` with usage instructions

**Files created/modified**: `u4-code-summary.md`, `env.example`, `README.md`

---

## Estimated Scope

| Category | Count |
|---|---|
| New source files | ~15 (routes, templates, static, services, glue) |
| Modified source files | 2 (`pyproject.toml`, `__init__.py`) |
| New test files | 9 |
| New vendor files | 4 (3Dmol.js, htmx.min.js, 2 license files) |
| Template files | 7 (base, list, new, detail, help, status fragment, error) |
| Total steps | 25 |
| Requirements covered | 22 FR + 4 NFR (all U4-owned requirements) |

---

## Execution Order Rationale

Steps 1–2 (deps + vendor) must come first — nothing compiles without them. Step 3 (app
factory) is the spine everything plugs into. Steps 4–6 (validation glue, upload, result
service) are leaf business logic with no template dependency, testable in isolation.
Steps 7–13 (routes) build on steps 3–6 and produce the URL surface. Steps 14–20 (templates
and static assets) are the visual layer; they are authored after routes so the template
variables are known. Step 21 (entry point) ties the app together. Step 22 (HTMX vendor)
could run earlier but is grouped with other static concerns. Step 23 (exports) is a single
edit best done when all new modules exist. Step 24 (tests) exercises everything. Step 25
(docs) records what was built.
