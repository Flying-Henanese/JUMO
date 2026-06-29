# Pre-Change Checklist

Use this before editing code, docs, Compose files, or harness guidance.

- Check `git status --short` and preserve unrelated user changes.
- Read the code path that owns the requested behavior before editing.
- Prefer `rg` and `rg --files` for discovery.
- Identify whether the task touches API routes, worker execution, parsing, storage,
  prompt construction, Docker, dependencies, tests, or docs.
- If README content disagrees with code, trust code and config first.
- Keep the change localized to the smallest responsible module.
- Avoid broad formatting, dependency churn, or generated file changes unless required.
- For architecture-level work, create a design in `.harness/designs/` before code changes.
- For multi-step implementation, create a plan in `.harness/plans/`.

