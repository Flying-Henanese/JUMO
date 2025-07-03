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
# 新版的mineru好像已经不在需要配置文件了
# os.environ['MINERU_TOOLS_CONFIG_JSON'] = 'config/mineru.json'
# 从国内的modelscope下载模型，避免huggingface无法访问的问题
os.environ['MINERU_MODEL_SOURCE'] = 'modelscope'
# os.environ['MINERU_MODEL_CACHE'] = '/data/.cache/modelscope/hub'
os.environ['MINERU_CONFIG_DIR'] = './config/'

# "MINERU_MAX_CONCURRENT_TASKS": None,
# 加载配置项
load_dotenv()
# 配置日志选项
setup_logger()
# 初始化各类需要被共享的资源
task_repository = TaskRepository()
minio_tool = MinioConnection()
pdf_processor = PDFProcessor(minio_tool=minio_tool, task_repository=task_repository)
thread_pool = ThreadPoolExecutor(max_workers=1)