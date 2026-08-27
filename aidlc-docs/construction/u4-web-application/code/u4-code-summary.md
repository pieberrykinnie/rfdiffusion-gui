# U4 Code Summary

This document summarizes the U4 Web Application code logic and components within `rfd-web`.

## FastAPI Setup
The main application is located in `rfd_web/app.py`. It uses FastAPI and jinja2 to serve the frontend interface. The `create_app` factory initializes required services (like `RunDirectoryReader`, `SubmissionService`, `PartitionCache`) and mounts the `rfd_web/routes` routers to handle various views.

## File Paths & Templates
All templates reside in `rfd_web/templates`. They use Jinja2 to render server-side state provided by `RunView` and services. We heavily use HTMX in fragments, such as `/runs/{id}/status` and `/api/preview-mode` for dynamic interactions without writing custom frontend Javascript.

## Routing
- **List Runs**: `rfd_web/routes/runs.py` implements the `/` list index page listing all submissions via `QueryService`.
- **Detail View**: `rfd_web/routes/detail.py` provides the detailed status, metadata, and 3D visualization viewer (via Molstar JS) for a run. HTMX provides run cancellation and polling on status.
- **Files Endpoints**: `rfd_web/routes/files.py` handles returning structure PDBs, trajectories, and a zip download for all run results. Paths are resolved via `RunDirectoryReader.resolve_within` to prevent path traversal.
- **Submit Form**: `rfd_web/routes/submit.py` powers `/new`, validating user-submitted configuration, writing them to `DesignRequest`, resolving templates, and launching Slurm jobs with `SubmissionService`.
