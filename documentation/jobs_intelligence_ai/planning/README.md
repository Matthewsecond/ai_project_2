# Planning

All planning docs live here, so there's one obvious home for "what are we doing".
Reference docs (ARCHITECTURE, TESTING) and per-module docs stay outside this folder.

## Active

| Plan | Status |
|---|---|
| [RESTRUCTURE_PLAN.md](RESTRUCTURE_PLAN.md) | **IN PROGRESS** — the modular rework + demo/production branch strategy. This is the plan we are executing now (Stage 2). |

> Currently the only active plan.

## Archive

Completed or superseded docs, kept for history only — **do not use for current work**.

| Doc | Why archived |
|---|---|
| [archive/CLEANUP_PLAN.md](archive/CLEANUP_PLAN.md) | **Completed.** The UX clunk-fix plan — all non-deferred items (P1–P4.1) landed. Only 4.2 (unify the `/chat` endpoints) stays deferred, and only if more chat surfaces appear. |
| [archive/SESSION_CONTEXT.md](archive/SESSION_CONTEXT.md) | **Superseded.** Describes the old Streamlit/EC2 design and a docx-spec build flow; the app is now Flask with the `src/` package layout. |
