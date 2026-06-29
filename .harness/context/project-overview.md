# Project Overview

JUMO / MinerU Service is a FastAPI + Celery document parsing service around
MinerU. It accepts source files from MinIO/S3-compatible object storage or direct
uploads, creates parsing tasks, runs heavy work in Celery workers, calls
vLLM-backed MinerU VLM inference for PDF/image extraction, and writes Markdown
plus structured artifacts back to object storage.

Use this file to understand what the project does and where the main code lives.
Use `architecture-map.md` for module boundaries, component wiring, data-flow
constraints, and risk areas before changing behavior.

## Core Capabilities

- Batch document task creation from MinIO prefixes via `/drop-pdf`.
- Single object task creation via `/analyze-pdf`.
- Upload and parse flow via `/upload-and-analyze-pdf`.
- Task status, batch status, artifact zip download, and reprocess APIs.
- Office and Markdown realtime helpers under `/realtime`.
- Content index loading and keyword coordinate search via `/search_pave` and
  `/content_search`.
- Semantic Markdown splitting, title/context preservation, table conversion,
  image caption enhancement, and NER-related helpers.
- CUDA and Ascend-oriented deployment modes through separate Compose files.

## Main Product Flows

### Asynchronous Document Parsing

1. A client submits an existing object, object prefix, or uploaded file.
2. The API creates one or more task records and enqueues task ids to Celery.
3. A worker downloads source bytes, normalizes supported formats to PDF when
   needed, and calls the active MinerU VLM parsing path.
4. The processor generates Markdown, structured JSON, extracted images, and split
   Markdown for later knowledge-base ingestion.
5. Status and download APIs expose task state and generated artifact paths.

### Realtime Office And Markdown Helpers

The `/realtime` routes bypass Celery for narrower synchronous operations:

- split submitted Markdown content or Markdown files;
- convert a single Office/Excel object from storage;
- convert a directory of Office/Excel objects;
- upload an Office/Excel file and stream Markdown back directly.

### Coordinate Search

After parsing, `/search_pave` can load a task's `*middle.json` into a cached
document index. `/content_search` then searches keywords and returns matching
page/span coordinate boxes so clients can highlight original document locations.

## Generated Artifacts

For a completed asynchronous task, `output_info` normally records these objects
under a task-id prefix in the output bucket:

- `markdown`: generated Markdown, e.g. `<task_id>/<name>.md`.
- `splitted_markdown`: Markdown after splitting, e.g.
  `<task_id>/<name>_splitted.md`.
- `content_list`: MinerU content-list JSON, e.g.
  `<task_id>/<name>_content_list.json`.
- `middle_json`: MinerU middle JSON with page/block/line/span structure, e.g.
  `<task_id>/<name>_middle.json`.
- `images`: extracted image objects under `<task_id>/images/`.

`/download-task-files/{task_id}` uses this JSON to stream a zip containing the
known outputs.

## Important Files

- `src/mineru_service.py`: FastAPI entry point and router registration.
- `src/startup.py`: dotenv loading, logger setup, shared task repository, and
  default MinIO connection initialization.
- `src/route/pdf_route.py`: asynchronous task APIs and task enqueueing.
- `src/route/documents_route.py`: realtime Office and Markdown helpers.
- `src/route/content_searching_route.py`: index loading and content search APIs.
- `src/celery_worker/celery_config.py`: Redis URL, queue, task, and device config.
- `src/celery_worker/celery_server.py`: Celery app and task dispatch helpers.
- `src/celery_worker/pdf_process_worker.py`: Celery worker entry point and task
  execution wrapper.
- `src/celery_worker/vllm_backend_start.py`: multi-device vLLM launcher.
- `src/processor/vlm_mode.py`: active VLM parsing pipeline orchestration.
- `src/processor/pdf_processor.py`: alternate MinerU pipeline-style processor.
- `src/processor/markdown_splitter.py`: Markdown splitting and chunking flow.
- `src/processor/content_indexing.py`: middle-JSON coordinate index and Redis cache.
- `src/wrapper/mineru_image_writer_wrapper.py`: image-write interception and
  optional image caption generation.
- `src/utils/minio_tool.py`: object storage access and request-scoped OSS clients.
- `src/data/model.py` and `src/data/operation.py`: task schema and repository.
- `docker-compose.yml`: default CUDA/NVIDIA-oriented local stack.
- `docker-compose-npu.yml`: Ascend/CANN-oriented stack.
- `pyproject.toml`: Python runtime and dependency source of truth.

## Documentation Status

README files are useful but may lag behind code. Verify API paths, container
names, environment variables, task names, storage object paths, and dependency
versions from source and Compose files before changing behavior or publishing
guidance.
