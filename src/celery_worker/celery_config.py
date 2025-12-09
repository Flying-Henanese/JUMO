import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    CELERY_BROKER_URL: str | None = os.getenv("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str | None = os.getenv("CELERY_RESULT_BACKEND")
    WORKER_QUEUE_NAME: str = os.getenv("WORKER_QUEUE_NAME", "celery")
    HF_ENDPOINT: str = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
    CUDA_VISIBLE_DEVICES: str = os.getenv("CUDA_VISIBLE_DEVICES", "0,1,2").strip()

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

def parse_cuda_devices() -> list[str]:
    """
    从环境变量中获取 CUDA_VISIBLE_DEVICES 配置，解析为设备列表。
    用于后续的 Celery 任务分配到不同的 GPU 设备上。
    
    :return: 解析后的 CUDA 设备列表
    """
    s = settings.CUDA_VISIBLE_DEVICES
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]

DEFAULT_QUEUE_NAME = settings.WORKER_QUEUE_NAME