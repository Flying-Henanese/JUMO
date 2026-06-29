# Verification Checklist

Use this before saying a task is complete.

- Inspect `git diff` for the touched files.
- Run `git diff --check` for whitespace and patch hygiene.
- For docs-only work, verify links, paths, commands, and names against source files.
- For route changes, inspect FastAPI decorators and expected request/response shapes.
- For Celery changes, verify producer task names, queue names, and worker registration match.
- For MinIO/OSS changes, verify bucket/object names and credential handling.
- For parsing changes, run the narrowest related tests or explain why they cannot run.
- For Docker or runtime changes, verify Compose service names, environment variables, and commands.
- State any unverified external dependencies plainly: GPU/NPU, vLLM, Redis, MinIO, model downloads, or network.

Suggested commands:

```bash
git diff --check
```

```bash
pytest tests/test_vlm_workflow.py
```

```bash
pytest tests/test_markdown_ner_integration.py tests/test_named_entity_recognition.py
```

```bash
ruff check .
```

