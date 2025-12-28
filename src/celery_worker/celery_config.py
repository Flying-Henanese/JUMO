"""
Celery configuration module.

This module handles configuration settings for Celery workers, including
broker URLs, Redis connections, and CUDA device parsing.

celery配置模块
这个模块用于管理所有和celery相关的配置项，包括：
- broker_url：celery消息队列的url
- result_backend：celery任务结果存储的url
- worker_queue_name：celery worker默认队列名称
- hf_endpoint：huggingface模型下载地址
- cuda_visible_devices：cuda可见设备列表

"""

from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    """
    Celery 配置类。
    包含所有和celery相关的配置项。
    """
    CELERY_BROKER_URL: str | None = os.getenv("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str | None = os.getenv("CELERY_RESULT_BACKEND")
    CELERY_REDIS_DB_BROKER: int = int(os.getenv("CELERY_REDIS_DB_BROKER", "0"))
    CELERY_REDIS_DB_BACKEND: int = int(os.getenv("CELERY_REDIS_DB_BACKEND", "1"))
    WORKER_QUEUE_NAME: str = os.getenv("WORKER_QUEUE_NAME", "celery")
    HF_ENDPOINT: str = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
    INFERENCE_DEVICES: str = os.getenv("INFERENCE_DEVICES", "0").strip()

settings = Settings()

def build_redis_url(db_index: int) -> str:
    """
    从环境变量中获取 Redis 配置，构建 Redis URL。
    :param db_index: Redis db数据库索引
    :return: 格式化后的 Redis URL
    """
    from data.redis.redis_client import get_redis_config_from_env
    # 从redis客户端获取配置
    # 这样的话可以和其他的模块共享配置（当前只有原文索引功能使用了redis）
    cfg = get_redis_config_from_env()
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 6379)
    username = cfg.get("username","")
    password = cfg.get("password")
    if password:
        return f"redis://{username}:{password}@{host}:{port}/{db_index}"
    return f"redis://{host}:{port}/{db_index}"

def parse_inference_devices() -> list[str]:
    """
    从环境变量中获取 INFERENCE_DEVICES 配置，解析为设备列表。
    用于后续的 Celery 任务分配到不同的 GPU/NPU 设备上。
    
    :return: 解析后的设备列表
    """
    s = settings.INFERENCE_DEVICES
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]

DEFAULT_QUEUE_NAME = settings.WORKER_QUEUE_NAME