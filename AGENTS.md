# Agent Instructions

This repository uses `.harness/` as the shared guidance layer for Codex and other
automation agents. Before making non-trivial changes, read this file and then
read the relevant harness files.

## Required Reading Order

1. `.harness/README.md`
2. `.harness/context/project-overview.md`
3. `.harness/context/architecture-map.md`
4. `.harness/context/runtime-and-config.md`
5. The checklist that matches the task:
   - `.harness/checklists/pre-change.md` before edits
   - `.harness/checklists/verification.md` before claiming completion
   - `.harness/checklists/security.md` for upload, OSS, prompt, auth, or parsing changes

## Working Rules

- Treat repository code as the source of truth. README files can be stale.
- Prefer small, localized changes that follow existing module boundaries.
- Do not rewrite unrelated docs or refactor unrelated code while handling a task.
- Keep `.harness/` files durable and project-specific. Do not store one-off chat notes there
  unless they belong in `.harness/runs/`.
- For significant design or architecture work, write the design under
  `.harness/designs/` and the implementation plan under `.harness/plans/`.
- For task execution records that should survive the conversation, add a dated note under
  `.harness/runs/`.

## Verification Expectations

- Run the narrowest useful verification for the touched area.
- For documentation-only changes, run `git diff --check`.
- For Python code changes, prefer focused `pytest` commands before broader suites.
- If Docker, GPU, NPU, Redis, MinIO, vLLM, or external model services are required but not
  available, state the verification limit explicitly.

