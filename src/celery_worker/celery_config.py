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
    CUDA_VISIBLE_DEVICES: str = os.getenv("CUDA_VISIBLE_DEVICES", "0,1,2,3").strip()

settings = Settings()

def build_redis_url(db_index: int) -> str:
    from data.redis.redis_client import get_redis_config_from_env
    cfg = get_redis_config_from_env()
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 6379)
    username = cfg.get("username","")
    password = cfg.get("password")
    if password:
        return f"redis://{username}:{password}@{host}:{port}/{db_index}"
    return f"redis://{host}:{port}/{db_index}"

def parse_cuda_devices() -> list[str]:
    s = settings.CUDA_VISIBLE_DEVICES
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]

DEFAULT_QUEUE_NAME = settings.WORKER_QUEUE_NAME