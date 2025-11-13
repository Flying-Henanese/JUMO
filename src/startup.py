"""
应用启动模块

负责初始化应用核心组件，包括：
- 环境变量配置
- 日志系统初始化
- 数据库连接
- 任务处理器初始化
- GPU选择补丁

"""
from dotenv import load_dotenv
# 这个作用是移除默认的stdout sinsk，并添加一些配置项
from utils.logging import setup_logger
from data.operation import TaskRepository
from utils.minio_tool import MinioConnection
# 应用猴子补丁，避免mineru原始代码中合并列表和文本时遇到的空值问题
from wrapper.merge_text import safe_merge_2_list_blocks,safe_merge_2_text_blocks
import mineru.backend.pipeline.para_split
mineru.backend.pipeline.para_split.__merge_2_list_blocks = safe_merge_2_list_blocks
mineru.backend.pipeline.para_split.__merge_2_text_blocks = safe_merge_2_text_blocks
# 应用猴子补丁，使用自定义的利用多进程的PDF转图片函数
from wrapper.pdf_boost_patch import load_images_from_pdf as custom_load_images_from_pdf
import mineru.utils.pdf_image_tools
mineru.utils.pdf_image_tools.load_images_from_pdf = custom_load_images_from_pdf
# 应用猴子补丁, 使用多线程进行
from wrapper.image_processing_boost import get_ocr_result_list_parallel
import mineru.utils.ocr_utils
mineru.utils.ocr_utils.get_ocr_result_list = get_ocr_result_list_parallel

# 应用猴子补丁，因为mineru输出的表格并不是标准的markdown格式而是html，
# 所以需要进行转换
from processor.converters.table_to_markdown import patch_batchanalyze_output_to_markdown    

# VLM模式使用下面的PDF处理器
#from processor.vlm_mode import PDFProcessor
#from processor.converters.table_to_markdown import patch_batchanalyze_output_to_markdown    
# 新版的mineru好像已经不在需要配置文件了

# 加载配置项
load_dotenv()
# 配置日志选项
setup_logger()
# 初始化各类需要被共享的资源
task_repository = TaskRepository()
minio_tool = MinioConnection()
patch_batchanalyze_output_to_markdown()
