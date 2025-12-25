"""
应用启动模块

负责初始化应用核心组件，包括：
- 日志系统初始化
- 数据库连接

"""
from dotenv import load_dotenv
# 这个作用是移除默认的stdout sinsk，并添加一些配置项
from utils.logging import setup_logger
from data.operation import TaskRepository
from utils.minio_tool import MinioConnection

# 加载配置项
load_dotenv()
# 配置日志选项
setup_logger()
# 初始化各类需要被共享的资源
task_repository = TaskRepository()
minio_tool = MinioConnection()
