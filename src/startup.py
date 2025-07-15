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
from concurrent.futures import ThreadPoolExecutor
from wrapper.merge_text import safe_merge_2_list_blocks,safe_merge_2_text_blocks
import mineru.backend.pipeline.para_split
# 应用猴子补丁
mineru.backend.pipeline.para_split.__merge_2_list_blocks = safe_merge_2_list_blocks
mineru.backend.pipeline.para_split.__merge_2_text_blocks = safe_merge_2_text_blocks
from processor.pdf_processor import PDFProcessor
from processor.converters.table_to_markdown import patch_batchanalyze_output_to_markdown    

# 新版的mineru好像已经不在需要配置文件了
# os.environ['MINERU_TOOLS_CONFIG_JSON'] = 'config/mineru.json'
# 从国内的modelscope下载模型，避免huggingface无法访问的问题
os.environ['MINERU_MODEL_SOURCE'] = 'modelscope'
# os.environ['MINERU_MODEL_CACHE'] = '~/.cache/modelscope/hub'
os.environ['MINERU_CONFIG_DIR'] = './config/'
os.environ['MINERU_DEVICE_MODE'] = f'cuda:{os.getenv("DEFAULT_CUDA_DEVICE", "0")}'
# os.environ['CUDA_VISIBLE_DEVICES'] = os.getenv('DEFAULT_CUDA_DEVICE', '0')
# "MINERU_MAX_CONCURRENT_TASKS": None,
# 加载配置项
load_dotenv()
# 配置日志选项
setup_logger()
# 初始化各类需要被共享的资源
task_repository = TaskRepository()
minio_tool = MinioConnection()
pdf_processor = PDFProcessor(minio_tool=minio_tool, task_repository=task_repository)
thread_pool = ThreadPoolExecutor(max_workers=int(os.getenv('MAX_CURRENT_WORKER', 1)))

patch_batchanalyze_output_to_markdown()
