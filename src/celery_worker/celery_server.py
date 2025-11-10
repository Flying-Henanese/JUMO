from celery import Celery
import os
from data.redis.redis_client import get_redis_config_from_env

# 用于生成celery broker和result backend的redis url
# 其实就是拼出来一个redis连接串
def build_redis_url(db_index: int) -> str:
    cfg = get_redis_config_from_env()
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 6379)
    password = cfg.get("password")
    if password:
        return f"redis://:{password}@{host}:{port}/{db_index}"
    return f"redis://{host}:{port}/{db_index}"

broker_url = os.getenv("CELERY_BROKER_URL") or build_redis_url(0)
result_backend = os.getenv("CELERY_RESULT_BACKEND") or build_redis_url(1)

celery_app: Celery = Celery("mineru_pdf", broker=broker_url, backend=result_backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
)
