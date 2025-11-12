from celery import Celery
import os
from data.redis.redis_client import get_redis_config_from_env
import redis

# 用于生成celery broker和result backend的redis url
# 其实就是拼出来一个redis连接串
def build_redis_url(db_index: int) -> str:
    cfg = get_redis_config_from_env()
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 6379)
    username = cfg.get("username","")
    password = cfg.get("password")
    if password:
        return f"redis://{username}:{password}@{host}:{port}/{db_index}"
    return f"redis://{host}:{port}/{db_index}"

broker_url = os.getenv("CELERY_BROKER_URL") or build_redis_url(0)
result_backend = os.getenv("CELERY_RESULT_BACKEND") or build_redis_url(1)
# 这里的celery_app等于是一个celery的客户端实例
# 生产者和消费者都要引用这个模块来访问celery队列, 来发送任务或者接收任务
celery_app: Celery = Celery("mineru_pdf", broker=broker_url, backend=result_backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
)

# 这些函数是给生产者用的，用来查询队列长度
# 这个模块上方的celery_app不会被重复实例化，因为路由部分的进程只有一个
def get_queue_length(queue_name: str) -> int:
    """
    查询 Redis broker 中某个 Celery 队列的等待任务数量（LLEN）。
    """
    cfg = get_redis_config_from_env()
    r = redis.Redis(host=cfg.get("host", "localhost"),
                    port=cfg.get("port", 6379),
                    password=cfg.get("password"),
                    db=0)  # broker db，默认0
    try:
        return int(r.llen(queue_name))
    except Exception:
        return 0

def parse_queue_names_from_env() -> list[str]:
    """
    从环境变量解析生产者可用的队列列表，形如: CELERY_QUEUE_NAMES=pdf_gpu1,pdf_gpu2
    若未设置则回退到默认 'celery' 队列。
    """
    s = os.getenv("CELERY_QUEUE_NAMES", "").strip()
    if not s:
        return ["celery"]
    return [q.strip() for q in s.split(",") if q.strip()]

def choose_queue_by_least_backlog(queue_names: list[str]) -> tuple[str, int]:
    """
    从给定队列列表中选择待处理数量最少的队列，返回 (队列名, backlog)。
    """
    lengths = [(q, get_queue_length(q)) for q in queue_names]
    return min(lengths, key=lambda x: x[1]) if lengths else ("celery", 0)

def send_pdf_task(task_id: str, queue: str) -> None:
    """
    通过任务名进行派发，避免在生产者侧导入沉重的 worker 模块。
    """
    celery_app.send_task("process_pdf", args=[task_id], queue=queue)
