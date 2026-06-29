# Unicum MinerU Service

Unicum MinerU Service is a document processing and content extraction service striving for high performance and asynchronous parsing. It provides RESTful APIs to convert various document formats (PDF, Office, Images) into structured Markdown content and performs reasonable splitting (based on article structure and semantic sentence clustering), followed by NER entity recognition. Finally, it offers indexing and search capabilities for the processed documents.

## Key Features

*   **Multi-Format Support**: Handles PDF, Word (`.doc`, `.docx`), PowerPoint (`.ppt`, `.pptx`), Excel (`.xls`, `.xlsx`, `.csv`), and Images (`.png`, `.jpg`, `.jpeg`).
*   **Asynchronous Processing**: Utilizes Celery and Redis for robust, distributed task management, suitable for high-concurrency workloads.
*   **GPU Acceleration**: Built-in support for Multi-GPU environments. By simply specifying GPU device numbers in the `.env` file, document parsing can be accelerated through multi-way parallelism.
*   **Content Indexing & Search**: Indexes processed documents to support keyword search with coordinate (bounding box) retrieval.
*   **S3/MinIO Integration**: Uses S3-compatible OSS services for file management, configurable in the `.env` file.

## Project Structure

The source code is organized as follows in the `src` directory:

*   **`mineru_service.py`**: The main entry point for the FastAPI application.
*   **`startup.py`**: Handles application startup routines, including logging setup and resource initialization (DB, MinIO).
*   **`celery_worker/`**: Contains the Celery worker implementation and configuration.
    *   `celery_server.py`: Configures the Celery app, broker, and queues.
    *   `pdf_process_worker.py`: The worker script that executes PDF processing tasks. Handles GPU allocation and resource initialization.
*   **`processor/`**: Core logic for document conversion and processing.
    *   `pdf_processor.py`: Orchestrates the conversion pipeline (e.g., Image/Office -> PDF -> Markdown).
    *   `content_indexing.py`: Services for building and querying document search indexes.
    *   `converters/`: Modules for specific format conversions (Doc to Markdown, Excel to Markdown, etc.).
*   **`route/`**: API route definitions.
    *   `pdf_route.py`: Endpoints for batch PDF processing (`/drop-pdf`).
    *   `documents_route.py`: Endpoints for synchronous Office file analysis (`/analyze-office-file`).
    *   `content_searching_route.py`: Endpoints for document indexing and searching (`/search_pave`, `/content_search`).
*   **`data/`**: Data layer components.
    *   `model.py`: SQLAlchemy ORM models (e.g., `Task`).
    *   `operation.py`: Database repositories.
    *   `redis/`: Redis client and cache services.
*   **`utils/`**: Utility modules (MinIO tool, logging, etc.).

## API Endpoints

### 1. Batch Document Processing
*   **Endpoint**: `POST /drop-pdf`
*   **Description**: Scans a specified path in MinIO, creates processing tasks for valid files, and pushes them to the Celery queue.
*   **Parameters**: `pdf_path`, `bucket_name`, `output_bucket`, `ocr_enabled`, etc.

### 2. Office File Analysis
*   **Endpoint**: `POST /analyze-office-file`
*   **Description**: Synchronously analyzes a Word or Excel file and returns the Markdown content.

### 3. Content Search
*   **Endpoint**: `POST /search_pave` & `GET /content_search`
*   **Description**: Load document indices and perform keyword searches to retrieve text segments and their coordinates.

## Getting Started

### Prerequisites
*   Python `>=3.10,<3.14`
*   Redis (for Celery broker/backend and caching)
*   MinIO (or S3-compatible storage)
*   Database (SQLAlchemy supported DBs)
*   NVIDIA GPU (optional, for acceleration)

### Configuration
Configuration is managed via environment variables (likely in a `.env` file). Key variables include:
*   `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
*   `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
*   `INFERENCE_DEVICES` (used by Docker Compose to select inference devices)

### Running the Service

Since I haven't pushed the image to Docker Hub yet, you'll need to build the image yourself using my Dockerfile.

```bash
docker build -t mineru-service .
```

Next, it is recommended to use Docker Compose to start the service, which will automatically manage all dependencies (API, Worker, Redis, vLLM).

**1. Start the Service:**
```bash
docker compose up -d
```
This will start the following containers:
*   `mineru-api`: FastAPI Service
*   `mineru-worker`: Celery Worker for processing PDFs
*   `vllm`: Inference Backend
*   `redis`: Message Queue and Cache

I have written what I consider to be comprehensive health check commands, ensuring that all modules are ready during the startup process.

**2. View Logs:**
```bash
docker compose logs -f
```

**3. Stop Service:**
```bash
docker compose down
```
