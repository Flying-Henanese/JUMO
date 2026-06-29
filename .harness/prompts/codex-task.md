# Codex Task Prompt Template

Use this template when starting a substantial Codex task in this repository.

```markdown
Read `AGENTS.md` first, then read the relevant `.harness/` files.

Task:
<describe the requested outcome>

Relevant area:
<route / processor / celery_worker / docker / docs / tests / harness>

Constraints:
- Preserve unrelated user changes.
- Keep edits localized.
- Verify against current source, not README alone.
- Record durable design, plan, or run notes under `.harness/` only when useful.

Expected verification:
<commands or evidence required>
```

