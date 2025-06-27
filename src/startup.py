"""
应用启动模块

负责初始化应用核心组件，包括：
- 环境变量配置
- 日志系统初始化
- 数据库连接
- 任务处理器初始化
- GPU选择补丁

"""
import os
from dotenv import load_dotenv
from utils.logging import setup_logger
from data.operation import TaskRepository
from utils.minio_tool import MinioConnection
from processor.pdf_processor import PDFProcessor
from concurrent.futures import ThreadPoolExecutor
from wrapper.gpu_patch import patch_gpu_selection


os.environ['MINERU_TOOLS_CONFIG_JSON'] = 'config/magic-pdf.json'
load_dotenv()
setup_logger()
task_repository = TaskRepository()
minio_tool = MinioConnection()
pdf_processor = PDFProcessor(minio_tool=minio_tool, task_repository=task_repository)
thread_pool = ThreadPoolExecutor(max_workers=1)
patch_gpu_selection() #打个补丁，确保每次调用may_batch_image_analyze时都会选择最佳的GPU