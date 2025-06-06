from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from enum import Enum
import uuid
from typing import Dict, OrderedDict
import asyncio
import uvicorn
import os
import json
import io
import tempfile
import dotenv
from minio import Minio
from minio.error import S3Error
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.data.data_reader_writer import FileBasedDataWriter
import pdb

app = FastAPI()
# 读取配置信息
dotenv.load_dotenv()
os.environ['MINERU_TOOLS_CONFIG_JSON'] = 'config/magic-pdf.json'
# MinIO 配置
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
# 默认的bucket名称
MINIO_BUCKET_NAME = "miners"
# 不使用HTTPS，将secure设置为False
MINIO_SECURE = False
# 默认输出文件的存储桶名称
MINIO_OUTPUT_BUCKET = "output"

# 初始化 MinIO 客户端
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

# 定义任务状态枚举
# 继承 str 类型，这样可以确保枚举值是字符串类型，而不是默认的 int 类型
# 这样可以确保在 JSON 序列化时，枚举值会被正确地转换为字符串
class TaskStatus(str, Enum):
    QUEUED = "排队中"
    PROCESSING = "处理中"
    COMPLETED = "处理完成"
    FAILED = "处理失败"

# 任务池类，用于管理任务的状态和队列
class TaskPool:

    def __init__(self, max_workers: int = 1, max_queue: int = 5):
        """
        初始化任务池，设置最大工作线程数和最大任务队列长度。
        """
        self.max_workers = max_workers
        self.max_queue = max_queue
        self.active_tasks: Dict[str, Dict] = {}
        self.queued_tasks = OrderedDict()
        self.lock = asyncio.Lock()


    async def add_task(self, task_id: str, task_data: Dict):
        """
        添加任务到任务池中，如果任务队列已满，则返回错误信息。
        如果有空闲的工作线程，则立即开始处理任务，否则将任务加入队列。
        """
        async with self.lock:
            if len(self.queued_tasks) >= self.max_queue:
                raise Exception("任务队列已满，请稍后再试")
            if len(self.active_tasks) < self.max_workers:
                self.active_tasks[task_id] = task_data
                return "processing"
            else:
                self.queued_tasks[task_id] = task_data
                return "queued"

    async def task_completed(self, task_id: str):
        """
        完成任务后，从活动任务列表中移除，并尝试从队列中获取下一个任务。
        如果队列中有任务，则返回下一个任务的ID，否则返回None。
        """
        async with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            if self.queued_tasks:
                next_task_id, next_task = self.queued_tasks.popitem(last=False)
                self.active_tasks[next_task_id] = next_task
                return next_task_id
            return None

    async def get_task_status(self, task_id: str):
        """
        通过taskid获取任务状态。
        如果任务在活动任务列表或队列中，则返回任务状态，否则返回None。
        """
        async with self.lock:
            if task_id in self.active_tasks:
                return self.active_tasks[task_id]["status"]
            elif task_id in self.queued_tasks:
                return self.queued_tasks[task_id]["status"]
            return None

# 初始化任务池和任务字典
# 默认同时只有一个任务在执行
task_pool = TaskPool(max_workers=1, max_queue=5)
tasks: Dict[str, Dict] = {}

@app.post("/analyze-pdf/")
async def analyze_pdf(pdf_path: str, background_tasks: BackgroundTasks, bucket_name: str = MINIO_BUCKET_NAME, output_bucket: str = MINIO_OUTPUT_BUCKET):
    try:
        # 校验文件是否存在
        minio_client.stat_object(bucket_name,pdf_path)
    except S3Error:
        raise HTTPException(status_code=404, detail="PDF文件未找到")
    task_id = str(uuid.uuid4()).replace("-", "")[:12]
    # 如果这个task_id已经存在，那么就重新生成一个task_id
    # 直到生成的task_id不在tasks字典中，或者对应的任务状态不是正在处理中的任务
    while task_id in tasks:
        task_id = str(uuid.uuid4()).replace("-", "")[:12]
    task_data = {
        "status": TaskStatus.QUEUED,
        "result": None,
        "error": None,
        "pdf_path": pdf_path,
    }
    # 将任务数据添加到任务字典中，开始处理流程
    tasks[task_id] = task_data

    try:
        # 将任务添加到任务池中
        placement = await task_pool.add_task(task_id, task_data)
        # 如果放入任务池的结果是"processing"，则立即开始处理任务
        # 如果放入任务池的结果是"queued"，则将任务加入队列，等待处理
        if placement == "processing":
            background_tasks.add_task(process_pdf_task, task_id = task_id, bucket_name = bucket_name, output_bucket = output_bucket)

        return JSONResponse(content={
            "task_id": task_id,
            "status": TaskStatus.QUEUED if placement == "queued" else TaskStatus.PROCESSING,
            "message": "任务已加入队列" if placement == "queued" else "任务正在处理"
        })
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return JSONResponse(content={
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"],
        "error": task["error"]
    })

tasks_lock = asyncio.Lock()  # 添加异步锁

async def process_pdf_task(task_id: str,bucket_name: str = MINIO_BUCKET_NAME,output_bucket: str = MINIO_OUTPUT_BUCKET):
    try:
        # 使用异步锁，防止同时对任务状态进行修改
        # 但这里其实也不会有同时修改的可能，还是加上吧
        async with tasks_lock:  
            tasks[task_id]["status"] = TaskStatus.PROCESSING

        pdf_object = minio_client.get_object(bucket_name, tasks[task_id]["pdf_path"])
        pdf_bytes = pdf_object.read()
        # 读取pdf文件为pymudoc对象
        ds = PymuDocDataset(pdf_bytes)
        # 获取pdf文件的名称，不包含后缀
        name_without_ext = os.path.splitext(os.path.basename(tasks[task_id]["pdf_path"]))[0]
        # 存储文档中所有的图片
        images_list = []
        # 使用临时文件进行相关的操作
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(output_dir, exist_ok=True)

            # 判断PDF文档类型是否需要使用OCR进行处理
            if ds.classify() == SupportedPdfParseMethod.OCR:
                # 如果是OCR类型，使用OCR模式进行分析
                infer_result = ds.apply(doc_analyze, ocr=True)
                # 为OCR模式也指定输出目录
                pipe_result = infer_result.pipe_ocr_mode(FileBasedDataWriter(output_dir))
            else:
                # 如果不是OCR类型，使用普通文本模式进行分析
                infer_result = ds.apply(doc_analyze, ocr=False)
                # 使用文本模式处理分析结果，并指定输出目录
                pipe_result = infer_result.pipe_txt_mode(FileBasedDataWriter(output_dir))
            
            # 提取并上传图片
            for root, _, files in os.walk(output_dir):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        with open(os.path.join(root, file), 'rb') as img_file:
                            # 先放入oss
                            minio_client.put_object(
                                output_bucket,
                                f"images/{name_without_ext}/{file}",
                                img_file,
                                os.path.getsize(os.path.join(root, file)),
                                content_type=f"image/{file.split('.')[-1]}"
                            )
                            # 然后再把图片名称放入图片列表
                            images_list.append(f"/images/{name_without_ext}/{file}")
            
            # 生成Markdown时指定OSS前缀
            markdown_content = pipe_result.get_markdown(
                img_dir_or_bucket_prefix=f"{output_bucket}/images/{name_without_ext}"
            )
            content_list = json.dumps(pipe_result.get_content_list(image_dir_or_bucket_prefix=output_dir))
            middle_json = pipe_result.get_middle_json()

            minio_client.put_object(
                output_bucket,
                f"{name_without_ext}.md",
                io.BytesIO(markdown_content.encode('utf-8')),
                length=len(markdown_content.encode('utf-8')),
                content_type="text/markdown"
            )

            minio_client.put_object(
                output_bucket,
                f"{name_without_ext}_content_list.json",
                io.BytesIO(content_list.encode('utf-8')),
                length=len(content_list.encode('utf-8')),
                content_type="application/json"
            )

            minio_client.put_object(
                output_bucket,
                f"{name_without_ext}_middle.json",
                io.BytesIO(middle_json.encode('utf-8')),
                length=len(middle_json.encode('utf-8')),
                content_type="application/json"
            )

        async with tasks_lock:
            tasks[task_id]["status"] = TaskStatus.COMPLETED
            tasks[task_id]["result"] = {
                "markdown": f"{name_without_ext}.md",
                "content_list": f"{name_without_ext}_content_list.json",
                "middle_json": f"{name_without_ext}_middle.json",
                "images": images_list
            }
    except S3Error as e:
        tasks[task_id]["status"] = TaskStatus.FAILED
        tasks[task_id]["error"] = str(e)
    except Exception as e:
        tasks[task_id]["status"] = TaskStatus.FAILED
        tasks[task_id]["error"] = str(e)
    finally:
        next_task_id = await task_pool.task_completed(task_id)
        if next_task_id:
            next_pdf_path = tasks[next_task_id].get("pdf_path")
            if next_pdf_path:
                await process_pdf_task(next_task_id)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)