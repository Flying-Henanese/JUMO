from celery import Celery
import os
from data.redis.redis_client import get_redis_config_from_env, RedisClient
from utils.logging import setup_logger
setup_logger()
from loguru import logger
# 这个后续会放到dockerfile中
os.environ['CUDA_VISIBLE_DEVICES'] = '1,2,3'

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
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_enable_remote_control=False,
    worker_send_task_events=False,
    broker_heartbeat=10,
    broker_transport_options={"health_check_interval": 30},
)

# 默认队列名称的单一来源，供 worker 任务装饰器与生产者参考
DEFAULT_QUEUE_NAME = os.getenv("WORKER_QUEUE_NAME", "celery")

def parse_cuda_devices() -> list[str]:
    """
    解析环境变量 CUDA_VISIBLE_DEVICES，以逗号分隔并去除空白。
    示例: CUDA_VISIBLE_DEVICES=0,1,2 -> ['0','1','2']
    若未设置或为空，返回空列表。
    """
    s = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]

# 这些函数是给生产者用的，用来查询队列长度
# 这个模块上方的celery_app不会被重复实例化，因为路由部分的进程只有一个
def get_queue_length(queue_name: str) -> int:
    """
    查询 Redis broker 中某个 Celery 队列的等待任务数量（LLEN），并包含已预取但未确认的任务。
    """
    # 复用项目内的 RedisClient，显式使用 broker 的 db=0，避免每次调用都新建连接
    if not hasattr(get_queue_length, "_client"):
        get_queue_length._client = RedisClient(db_index=0).get_client()
    r = get_queue_length._client

    # 等待中的任务（队列长度）
    waiting = 0
    try:
        # Primary: 原始队列键（不带前缀）
        waiting = int(r.llen(queue_name))
    except Exception:
        waiting = 0

    # Fallback: Celery 可能使用 "queue:<name>" 作为列表键
    if waiting == 0:
        try:
            alt = f"queue:{queue_name}"
            t = r.type(alt)
            if t == b"list" or t == "list":
                waiting = int(r.llen(alt))
        except Exception:
            pass

    return waiting

def parse_queue_names_from_env() -> list[str]:
    return [DEFAULT_QUEUE_NAME]

def choose_queue_by_least_backlog(queue_names: list[str]) -> tuple[str, int]:
    """
    从给定队列列表中选择待处理数量最少的队列
    返回格式： (队列名, backlog)。
    """
    lengths = [(q, get_queue_length(q)) for q in queue_names]
    logger.info(f"队列长度: {lengths}")
    return min(lengths, key=lambda x: x[1]) if lengths else (DEFAULT_QUEUE_NAME, 0)

def send_pdf_task(task_id: str, queue: str) -> None:
    """
    通过任务名进行派发，避免在生产者侧导入沉重的 worker 模块。
    """
    celery_app.send_task("process_pdf", args=[task_id], queue=queue)
