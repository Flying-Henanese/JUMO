from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from enum import Enum

from utils.minio_tool import MinioConnection
import uuid
from typing import Dict, OrderedDict
from concurrent.futures import ThreadPoolExecutor
import asyncio
import uvicorn
from threading import Lock
import os
import json
import tempfile
from dotenv import load_dotenv
from minio.error import S3Error
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.data.read_api import read_local_images, read_local_office
from wrapper.gpu_patch import patch_gpu_selection
patch_gpu_selection() #打个补丁，确保每次调用may_batch_image_analyze时都会选择最佳的GPU
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.data.data_reader_writer import FileBasedDataWriter

app = FastAPI()

# 读取配置信息
load_dotenv()
os.environ['MINERU_TOOLS_CONFIG_JSON'] = 'config/magic-pdf.json'
# 预定义的文件类型
PDF_EXTENSIONS = [".pdf"]
OFFICE_EXTENSIONS = [".ppt", ".pptx", ".doc", ".docx"]
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"]

# 加载minio连接模块
minio_tool = MinioConnection()
# 创建线程池
thread_pool = ThreadPoolExecutor(max_workers=1)
# 异步锁
tasks_lock = Lock()  # 添加异步锁

# 定义任务状态枚举
# 继承 str 类型，这样可以确保枚举值是字符串类型，而不是默认的 int 类型
# 这样可以确保在 JSON 序列化时，枚举值会被正确地转换为字符串
class TaskStatus(str, Enum):
    QUEUED = "排队中"
    PROCESSING = "处理中"
    COMPLETED = "处理完成"
    FAILED = "处理失败"

class TaskPool:

    def __init__(self, max_workers: int = 1, max_queue: int = 5):
        """
        初始化任务池，设置最大工作线程数和最大任务队列长度。
        """
        self.max_workers = max_workers
        self.max_queue = max_queue
        self.active_tasks: Dict[str, Dict] = {}
        self.queued_tasks = OrderedDict()
        self.lock = Lock()

    def add_task(self, task_id: str, task_data: Dict):
        """
        添加任务到任务池中，如果任务队列已满，则返回错误信息。
        如果有空闲的工作线程，则立即开始处理任务，否则将任务加入队列。
        """
        with self.lock:
            if len(self.queued_tasks) >= self.max_queue:
                raise Exception("任务队列已满，请稍后再试")
            if len(self.active_tasks) < self.max_workers:
                self.active_tasks[task_id] = task_data
                return "processing"
            else:
                self.queued_tasks[task_id] = task_data
                return "queued"

    def task_completed(self, task_id: str):
        """
        完成任务后，从活动任务列表中移除，并尝试从队列中获取下一个任务。
        如果队列中有任务，则返回下一个任务的ID，否则返回None。
        """
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            if self.queued_tasks:
                next_task_id, next_task = self.queued_tasks.popitem(last=False)
                self.active_tasks[next_task_id] = next_task
                return next_task_id
            return None

    def get_task_status(self, task_id: str):
        """
        通过taskid获取任务状态。
        如果任务在活动任务列表或队列中，则返回任务状态，否则返回None。
        """
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
async def analyze_pdf(
    pdf_path: str, 
    background_tasks: BackgroundTasks, 
    bucket_name: str, 
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: str = "chi_sim",
    ):
    try:
        # 校验文件是否存在
        minio_tool.file_exists(bucket_name = bucket_name,object_name=pdf_path)
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
        "bucket_name": bucket_name,
        "output_bucket": output_bucket
    }
    # 将任务数据添加到任务字典中，开始处理流程
    tasks[task_id] = task_data

    try:
        # 将任务添加到任务池中
        placement = task_pool.add_task(task_id, task_data)
        # 如果放入任务池的结果是"processing"，则立即开始处理任务
        # 如果放入任务池的结果是"queued"，则将任务加入队列，等待处理
        if placement == "processing":
            with tasks_lock:
                tasks[task_id]["status"] = TaskStatus.PROCESSING
            background_tasks.add_task(
                process_pdf_task, 
                task_id = task_id, 
                bucket_name = bucket_name, 
                output_bucket = output_bucket,
                ocr_enabled = ocr_enabled,
                table_enabled = table_enabled,
                ocr_lang = ocr_lang
                )

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

def _sync_process_pdf(
    task_id: str,
    bucket_name: str,
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: str = "chi_sim"):
    try:
        # 使用异步锁，防止同时对任务状态进行修改
        # 但这里其实也不会有同时修改的可能，还是加上吧
        with tasks_lock:  
            tasks[task_id]["status"] = TaskStatus.PROCESSING
        extention = os.path.splitext(tasks[task_id]["pdf_path"])[-1]
        file_bytes = minio_tool.get_file_byte(bucket_name = bucket_name,object_name = tasks[task_id]["pdf_path"])
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            # 把文件保存在临时文件夹中
            with open(os.path.join(temp_dir, os.path.basename(tasks[task_id]["pdf_path"])), "wb") as f:
                f.write(file_bytes)
                # 读取pdf文件为pymudoc对象
                if extention in PDF_EXTENSIONS:
                    # 读取pdf文件为pymupdf数据集
                    ds = PymuDocDataset(file_bytes)
                elif extention in OFFICE_EXTENSIONS:
                    # 需要使用office解析器把文档解析为pymudoc数据列表
                    ds = read_local_office(temp_dir)[0]
                elif extention in IMAGE_EXTENSIONS:
                    # 读取图片文件为一个数据集
                    ds = read_local_images(temp_dir)[0]
                else:
                    raise HTTPException(status_code=400, detail="不支持的文件类型")
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
                infer_result = ds.apply(
                    doc_analyze, 
                    ocr=ocr_enabled, # 如果支持OCR,就按照用户传参指定是否使用
                    table_enable = table_enabled,
                    lang = ocr_lang )
                # 为OCR模式也指定输出目录
                pipe_result = infer_result.pipe_ocr_mode(FileBasedDataWriter(output_dir))
            else:
                # 如果不是OCR类型，使用普通文本模式进行分析
                infer_result = ds.apply(doc_analyze, ocr=False)
                # 使用文本模式处理分析结果，并指定输出目录
                pipe_result = infer_result.pipe_txt_mode(FileBasedDataWriter(output_dir))
            
            # 提取并上传图片
            # 同时将图片
            for root, _, files in os.walk(output_dir):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        with open(os.path.join(root, file), 'rb') as img_file:
                            # 把图片先放入oss
                            minio_tool.upload_file_by_bytes(
                                bucket_name = output_bucket,
                                object_name=f"{task_id}/images/{file}",
                                file_bytes=img_file.read(),
                                content_type=f"image/{file.split('.')[-1]}"
                            )
                            # 然后再把图片名称放入图片列表
                            images_list.append(f"{task_id}/images/{file}")
            
            # 生成核心的3个文件
            # 1. markdown文件
            markdown_content = pipe_result.get_markdown(
                img_dir_or_bucket_prefix=f"{task_id}/images/"
            )
            # 2. content_list文件
            content_list = json.dumps(pipe_result.get_content_list(image_dir_or_bucket_prefix=output_dir))
            # 3. middle_json文件
            middle_json = pipe_result.get_middle_json()


            # 把生成的3个文件全部放入OSS
            minio_tool.upload_file_by_bytes(
                bucket_name = output_bucket,
                object_name=f"{task_id}/{name_without_ext}.md",
                file_bytes=markdown_content.encode('utf-8'),
                content_type="text/markdown"
            )

            minio_tool.upload_file_by_bytes(
                bucket_name = output_bucket,
                object_name=f"{task_id}/{name_without_ext}_content_list.json",
                file_bytes=content_list.encode('utf-8'),
                content_type="application/json"
            )

            minio_tool.upload_file_by_bytes(
                bucket_name = output_bucket,
                object_name=f"{task_id}/{name_without_ext}_middle.json",
                file_bytes=middle_json.encode('utf-8'),
                content_type="application/json"
            )

        with tasks_lock:
            tasks[task_id]["status"] = TaskStatus.COMPLETED
            tasks[task_id]["result"] = {
                "markdown": f"{task_id}/{name_without_ext}.md",
                "content_list": f"{task_id}/{name_without_ext}_content_list.json",
                "middle_json": f"{task_id}/{name_without_ext}_middle.json",
                "images": images_list
            }
    except S3Error as e:
        tasks[task_id]["status"] = TaskStatus.FAILED
        tasks[task_id]["error"] = str(e)
    except Exception as e:
        tasks[task_id]["status"] = TaskStatus.FAILED
        tasks[task_id]["error"] = str(e)

        
async def process_pdf_task(
    task_id: str,
    bucket_name: str,
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: str = "chi_sim"):
    loop = asyncio.get_running_loop()
    try:
        # 将同步阻塞函数放到线程池中执行
        result = await loop.run_in_executor(
            thread_pool,
            _sync_process_pdf,  # 同步处理函数
            task_id, 
            tasks[task_id]["bucket_name"], 
            tasks[task_id]["output_bucket"],
            ocr_enabled,
            table_enabled,
            ocr_lang
        )
        return result
    except Exception as e:
        # 错误处理已经在_sync_process_pdf内部完成，这里只是为了捕获未处理的异常
        print(f"Error in process_pdf_task for {task_id}: {e}")
        # 如果_sync_process_pdf已经处理了错误并更新了tasks，这里可以不做额外处理
        # 否则，可以在这里更新tasks[task_id]["status"] = TaskStatus.FAILED
    finally:
        # 任务完成后，从任务池中移除任务，并获取下一个任务ID
        next_task_id = task_pool.task_completed(task_id)

        # 检查是否有下一个任务需要启动
        if next_task_id:
            with tasks_lock: # 保护全局tasks字典
                tasks[next_task_id]["status"] = TaskStatus.PROCESSING
            # 关键：在这里使用 asyncio.create_task 或 BackgroundTasks 调度下一个任务
            # 因为 process_pdf_task 运行在主事件循环中，可以安全地调度异步任务
            # 注意：这里直接使用 asyncio.create_task 更符合内部调度，
            # 如果想让FastAPI管理，也可以考虑重新调用 analyze_pdf 接口
            # 但内部调度更合适，避免了HTTP请求的开销

            # 方式A: 使用 asyncio.create_task (推荐用于内部调度)
            asyncio.create_task(
                process_pdf_task(
                    next_task_id,
                    tasks[task_id]["bucket_name"], 
                    tasks[task_id]["output_bucket"]
                    )
                )
            print(f"Task {next_task_id} started from queue.")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)