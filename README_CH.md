# Unicum MinerU Service

Unicum MinerU Service 是一个努力实现高性能和异步解析的文档处理和内容提取服务。它提供 RESTful API，将各种文档格式（PDF、Office、图像）转换为结构化的 Markdown 内容并进行合理地切分（基于文章结构和句子的语义聚集），而后实施NER实体识别。最后，提供处理后文档的索引和搜索功能。

## 主要特性

*   **多格式支持**：处理 PDF、Word（`.doc`, `.docx`）、PowerPoint（`.ppt`, `.pptx`）、Excel（`.xls`, `.xlsx`, `.csv`）和图像（`.png`, `.jpg`, `.jpeg`）。
*   **异步处理**：利用 Celery 和 Redis 进行分布式任务管理，适用于较高并发工作负载。
*   **GPU 加速**：内置对多 GPU 环境的支持，只要在.env文件中指定GPU设备的编号，即可通过多路并行的方式加速文档解析。
*   **内容索引与搜索**：索引处理后的文档，支持带有坐标（边界框）检索的关键字搜索。
*   **S3/MinIO 集成**：使用s3 compatible的OSS服务进行文件管理，可在.env文件中自行配置。

## 项目结构

源代码在 `src` 目录中组织如下：

*   **`mineru_service.py`**：FastAPI 应用程序的主要入口点。
*   **`startup.py`**：处理应用程序启动例程，包括日志设置和资源初始化（DB、MinIO）。
*   **`celery_worker/`**：包含 Celery worker 的实现和配置。
    *   `celery_server.py`：配置 Celery 应用、代理和队列。
    *   `pdf_process_worker.py`：执行 PDF 处理任务的 worker 脚本。处理 GPU 分配和资源初始化。
*   **`processor/`**：文档转换和处理的核心逻辑。
    *   `pdf_processor.py`：编排转换流程（例如，图像/Office -> PDF -> Markdown）。
    *   `content_indexing.py`：构建和查询文档搜索索引的服务。
    *   `converters/`：特定格式转换的模块（Doc 转 Markdown，Excel 转 Markdown 等）。
*   **`route/`**：API 路由定义。
    *   `pdf_route.py`：批量 PDF 处理的端点（`/drop-pdf`）。
    *   `documents_route.py`：同步 Office 文件分析的端点（`/analyze-office-file`）。
    *   `content_searching_route.py`：文档索引和搜索的端点（`/search_pave`, `/content_search`）。
*   **`data/`**：数据层组件。
    *   `model.py`：SQLAlchemy ORM 模型（例如，`Task`）。
    *   `operation.py`：数据库存储库。
    *   `redis/`：Redis 客户端和缓存服务。
*   **`utils/`**：实用模块（MinIO 工具、日志记录等）。

## API 端点

### 1. 批量文档处理
*   **端点**：`POST /drop-pdf`
*   **描述**：扫描 MinIO 中的指定路径，为有效文件创建处理任务，并将其推送到 Celery 队列。
*   **参数**：`pdf_path`, `bucket_name`, `output_bucket`, `ocr_enabled` 等。

### 2. Office 文件分析
*   **端点**：`POST /analyze-office-file`
*   **描述**：同步分析 Word 或 Excel 文件并返回 Markdown 内容。

### 3. 内容搜索
*   **端点**：`POST /search_pave` & `GET /content_search`
*   **描述**：加载文档索引并执行关键字搜索以检索文本段及其坐标。

## 快速开始

### 先决条件
*   Python 3.11+
*   Redis（用于 Celery 代理/后端和缓存）
*   MinIO（或 S3 兼容存储）
*   数据库（支持 SQLAlchemy 的数据库）
*   NVIDIA GPU（可选，用于加速）

### 配置
配置通过环境变量管理（可能在 `.env` 文件中）。关键变量包括：
*   `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
*   `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
*   `CUDA_VISIBLE_DEVICES`（由 worker 自动管理）

### 运行服务
因为我还没有把镜像推送到docker hub服务，所以只能你自己使用我的dockerfile进行镜像制作了。
```bash
docker build -t mineru-service .
```
接下来推荐使用 Docker Compose 启动服务，这将自动管理所有依赖项（API、Worker、Redis、vLLM）。
**1. 启动服务：**
```bash
docker compose up -d
```
这将启动以下容器：
*   `mineru-api`: FastAPI 服务
*   `mineru-worker`: Celery Worker 用于处理 PDF
*   `vllm`: 推理后端
*   `redis`: 消息队列和缓存

我编写了自认为完备的健康检查命令，启动过程会保证各模块均已就位。

**2. 查看日志：**
```bash
docker compose logs -f
```

**3. 停止服务：**
```bash
docker compose down
```

