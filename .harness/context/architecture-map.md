# Architecture Map

Use this file before changing code. It defines component wiring, module
ownership, data flow, and risk boundaries. Use `project-overview.md` first when
you only need a quick understanding of what the service does.

## Runtime Components

- API service: FastAPI process started from `src/mineru_service.py`; registers
  document-task, realtime-document, and content-search routers.
- Task producer: `src/route/pdf_route.py`; creates `Task` rows and sends task
  ids through `celery_worker.celery_server.send_pdf_task(...)`.
- Worker service: Celery worker started from
  `src/celery_worker/pdf_process_worker.py`; consumes the configured queue and
  runs the active parsing processor.
- Inference service: vLLM OpenAI-compatible HTTP servers started by
  `src/celery_worker/vllm_backend_start.py`; one instance is started per
  `INFERENCE_DEVICES` entry.
- Broker/backend/cache: Redis is used as Celery broker, Celery result backend,
  and content-search cache. Keep these roles distinct when changing Redis code.
- Storage: MinIO or S3-compatible OSS, accessed through `utils.minio_tool`.
  `/analyze-pdf` can persist request-scoped OSS credentials for worker reuse.
- Persistence: SQLAlchemy task repository backed by SQLite by default. Local
  Compose mounts `database/` so API and worker containers share the same file.

## Component Communication

- API -> Celery: send only the task id and queue name. Avoid importing heavy
  processor modules into route code.
- Worker -> database: load the task row, mark `PROCESSING`, update
  `output_info`, then mark `COMPLETED` or `FAILED`.
- Worker -> object storage: download source bytes from the input bucket and
  upload generated artifacts to the output bucket.
- Worker -> vLLM: call MinerU hybrid VLM analysis with `backend="http-client"`
  and `server_url` from `VLLM_SERVER_URL`.
- API/search -> Redis: load and retrieve serialized document indexes for keyword
  coordinate search.
- API/download -> object storage: read artifact paths from `output_info` and
  stream a zip to the caller.

## Main Async Request Flow

1. Route validates source object or upload, output bucket, supported extension,
   queue pressure, and optional request-scoped OSS connection.
2. Route creates a `Task` row with source bucket/key, output bucket, OCR/table
   flags, formula flags, inline-formula flag, OCR language, and optional OSS
   credential fields.
3. Route publishes the task id to Celery through `send_pdf_task`.
4. Worker receives `process_pdf`, reloads the task row, and marks it
   `PROCESSING`.
5. Worker calls `processor.vlm_mode.PDFProcessor._sync_process_pdf(...)`.
6. Processor downloads bytes, converts image/Office/Excel inputs to PDF when
   needed, and calls MinerU VLM analysis through the configured vLLM endpoint.
7. Processor uploads Markdown, split Markdown, content list, middle JSON, and
   extracted images to the output bucket.
8. Processor writes artifact paths to `Task.output_info`.
9. Worker completes the task with `COMPLETED` or `FAILED`.
10. Status, batch-status, download, reprocess, and search routes read from the
    task row and generated object paths.

## Key Data Structures

- `Task.status`: current lifecycle state. Active status checks treat `QUEUED`
  and `PROCESSING` as active.
- `Task.output_info`: JSON string on success; plain error text is possible on
  failure. Parse defensively in API responses.
- `output_info.markdown`: `<task_id>/<name>.md`.
- `output_info.splitted_markdown`: `<task_id>/<name>_splitted.md`.
- `output_info.content_list`: `<task_id>/<name>_content_list.json`.
- `output_info.middle_json`: `<task_id>/<name>_middle.json`.
- `output_info.images`: list of objects under `<task_id>/images/`.
- Content-search index: built from `middle_json`, cached in Redis as
  `document_index:<task_id>`, then queried by `/content_search`.

## Module Boundary Rules

- `route/`: validate inputs, translate HTTP request/response shapes, create or
  query task records, enqueue work, and call narrow service APIs. Do not place
  parsing, conversion, VLM prompt construction, or storage traversal algorithms
  here unless they are strictly request validation.
- `processor/`: own parsing, conversion, Markdown splitting, content indexing,
  image enhancement, NER, and VLM/image-caption behavior. Keep HTTP concerns out
  of this layer except for explicit integration clients.
- `data/`: own SQLAlchemy models/repositories and Redis wrappers. Do not call
  FastAPI response helpers or MinerU processors from this layer.
- `utils/`: hold cross-cutting support such as logging, object-storage access,
  id generation, device selection, and worker thread pools. Avoid hiding domain
  parsing decisions here.
- `wrapper/`: keep MinerU monkey patches, adapters, and integration shims here.
  Do not turn wrappers into general business-logic modules.
- `celery_worker/`: own Celery configuration, worker process lifecycle, task
  registration, and vLLM process launching. Keep task payload contracts stable.
- `const/`: enums and extension/status constants only.

## Processor Selection

- The live Celery worker imports `PDFProcessor` from `processor.vlm_mode`.
- `processor.vlm_mode.PDFProcessor` is the active VLM path and uses MinerU
  hybrid analysis over an HTTP vLLM backend.
- `processor.pdf_processor.PDFProcessor` is still present as an alternate
  pipeline-style processor, but it is not the current worker import path.
- Before changing parsing behavior, verify the actual import path in
  `src/celery_worker/pdf_process_worker.py`.

## Deployment Boundaries

- `docker-compose.yml` is the CUDA/NVIDIA-oriented stack. Service names:
  `jumo-api`, `jumo-worker`, `jumo-vllm`, `redis`.
- `docker-compose-npu.yml` is the Ascend/NPU-oriented stack. Service names:
  `mineru-api`, `mineru-worker`, `mineru-vllm`, `mineru-redis`.
- API depends on Redis and worker; worker depends on Redis and vLLM.
- vLLM health checks call `/v1/models` on each configured per-device port.
- `TASK_NAME_PROCESS_PDF` must match producer and worker registration. Default:
  `process_pdf`.
- `WORKER_QUEUE_NAME` must match producer queue and worker `-Q` queue. Default:
  `celery`.
- Redis broker and backend default to separate DBs:
  `CELERY_REDIS_DB_BROKER=0`, `CELERY_REDIS_DB_BACKEND=1`.
- vLLM routing is device-index based: worker index `i` uses
  `http://<VLLM_BASE_ENDPOINT>:<VLLM_BASE_PORT + i>/v1`.

## Risk Areas

- Uploaded files and parsed document text are untrusted input.
- VLM prompts and image captions must treat document content as data, not
  instructions.
- `wrapper/mineru_image_writer_wrapper.py` can call an external multimodal VLM;
  avoid leaking secrets or trusting generated captions as authoritative facts.
- OSS credentials can be request-scoped and persisted on `Task`; do not log
  `oss_secret_key` or include it in public responses.
- Celery uses late ack and worker child restart settings; interrupted work can
  be executed more than once. Changes must tolerate duplicate processing.
- SQLite is shared by API and worker containers through a mounted file in local
  Compose; avoid assumptions that only one process writes task state.
- Redis has multiple roles. Changing DB selection or key names can break Celery
  and content search independently.
- Object paths in `output_info` are the contract for status, download, and search
  follow-up APIs. Keep additions backward-compatible.
- Docker, GPU/NPU, vLLM, Redis, MinIO, model downloads, and external VLM APIs can
  block full integration verification in local environments.

## Change Routing Guide

- API request/response behavior: start in `src/route/*`, then inspect affected
  repository, storage, or processor calls.
- Task lifecycle or queue behavior: inspect `celery_worker/celery_server.py`,
  `celery_worker/pdf_process_worker.py`, and `data/operation.py` together.
- Parsing output changes: inspect `processor/vlm_mode.py`,
  `processor/markdown_splitter.py`, and relevant `processor/converters/*`.
- Coordinate search changes: inspect `route/content_searching_route.py`,
  `processor/content_indexing.py`, and Redis cache wrappers.
- Storage or credential behavior: inspect `utils/minio_tool.py`,
  `route/pdf_route.py`, and `data/model.py`.
- Deployment/env changes: inspect `runtime-and-config.md`, Compose files, and
  `celery_worker/celery_config.py`.
