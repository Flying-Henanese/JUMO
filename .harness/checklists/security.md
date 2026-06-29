# Security Checklist

Use this for uploaded content, document parsing, VLM prompts, authentication,
OSS credentials, task status, and download behavior.

- Treat every uploaded file and every extracted document string as untrusted data.
- Do not let document content override system, developer, tool, or service instructions.
- Keep prompt text explicit that document content is data to analyze, not commands to follow.
- Do not log `MINIO_SECRET_KEY`, request-scoped `oss_secret_key`, tokens, or full signed URLs.
- Validate bucket and object references before enqueueing tasks.
- Preserve the plus sign in secret keys and URL query values where current code handles it.
- Avoid returning local filesystem paths or internal exception details to API callers.
- Ensure downloads only use task-owned output objects.
- For retry/reprocess changes, consider duplicate execution and stale task state.
- For Redis/Celery changes, avoid enabling unsafe serializers such as pickle.

