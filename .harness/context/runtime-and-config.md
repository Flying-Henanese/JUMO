# Runtime And Configuration

## Python And Dependencies

- Runtime Python: `>=3.10,<3.14` from `pyproject.toml`.
- Dependency manager/build metadata: Poetry / `poetry-core`.
- Main runtime dependencies include FastAPI, Uvicorn, Celery, MinerU, vLLM, MinIO,
  SQLAlchemy, Transformers, Docling, sentence-transformers, and NLTK.
- Dev tooling includes pytest and Ruff.

## Local Verification Commands

Use focused commands first:

```bash
git diff --check
```

```bash
pytest
```

```bash
pytest tests/test_vlm_workflow.py
```

```bash
ruff check .
```

Some commands may require the local environment to have the large runtime stack
installed. If dependencies, GPU/NPU, vLLM, Redis, or MinIO are unavailable, report
that limitation instead of implying full verification.

## Docker Compose

Default stack:

```bash
docker build -t mineru-service:latest .
docker compose up -d
```

NPU stack:

```bash
docker compose -f docker-compose-npu.yml up -d
```

Important environment variables:

- `API_SERVICE_PORT`
- `INFERENCE_DEVICES`
- `MODEL`
- `MINERU_MODEL_SOURCE`
- `VLLM_BASE_ENDPOINT`
- `VLLM_RPC_TIMEOUT`
- `WORKER_QUEUE_NAME`
- `TASK_NAME_PROCESS_PDF`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `CELERY_REDIS_DB_BROKER`, `CELERY_REDIS_DB_BACKEND`
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_SECURE`
- `MINIO_BUCKET_NAME`, `MINIO_OUTPUT_BUCKET`, `UPLOAD_BUCKET`

## API Surface To Verify From Code

- `POST /drop-pdf`
- `POST /analyze-pdf`
- `POST /upload-and-analyze-pdf`
- `GET /task-status/{task_id}`
- `GET /download-task-files/{task_id}`
- `POST /reprocess-task/{task_id}`
- `POST /batch-task-status`
- `POST /realtime/split-markdown-file`
- `POST /realtime/analyze-office-file`
- `POST /realtime/analyze-office-dir`
- `POST /search_pave`
- `GET /content_search`

