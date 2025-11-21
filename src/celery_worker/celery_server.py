from celery import Celery
import os
from data.redis.redis_client import get_redis_config_from_env, RedisClient
from utils.logging import setup_logger
setup_logger()
from loguru import logger
from .celery_config import settings, build_redis_url, DEFAULT_QUEUE_NAME

# 这个后续会放到dockerfile中
os.environ['CUDA_VISIBLE_DEVICES'] = '1,2,3'

# 模块常量：统一任务名
TASK_NAME_PROCESS_PDF = "process_pdf"

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

broker_url = settings.CELERY_BROKER_URL or build_redis_url(0)
result_backend = settings.CELERY_RESULT_BACKEND or build_redis_url(1)

# 这里的celery_app等于是一个celery的客户端实例
# 生产者和消费者都要引用这个模块来访问celery队列, 来发送任务或者接收任务
celery_app: Celery = Celery(
    # 这里的main是celery的app name，不起实际作用
    main="mineru_pdf", 
    # broker是celery的消息队列，这里用的是redis
    broker=broker_url, 
    # 值得注意的是这里消息和结果放在了两个不同的redis db中
    backend=result_backend
    )

celery_app.conf.update(
    # 任务序列化格式使用 JSON，避免不安全的 pickle；生产环境更安全
    task_serializer="json",
    # 仅接受 JSON 内容，拒绝其它格式（如 pickle），提升安全性与一致性
    accept_content=["json"],
    # 任务结果序列化为 JSON，便于后端存储与调试查看
    result_serializer="json",
    # 指定任务/日志时区为上海
    timezone="Asia/Shanghai",
    # 禁用 UTC，配合上面的本地时区；如需跨区统一时间可改为 True
    enable_utc=False,
    # 每个 worker 一次只预取 1 条，避免任务堆积在单个 worker，提升公平性
    # 注意！：曾经试过把这个设为0，结果是worker反而会饥不择食疯狂消费，导致你根本找不到有等待处理的任务（因为都被worker扒自己碗里了）
    worker_prefetch_multiplier=1,
    # 任务处理完成后才确认（ack）；异常/崩溃时可重投递，提升可靠性
    # 注意！：但是会造成一个任务多次执行的问题（因为任务在执行过程中如果中断，还来不及更新ack，下次重启就会被认为这个任务还未执行）
    task_acks_late=True,
    # 关闭 worker 远程控制（广播），减少开销与安全面；如需 Flower 控制可开启
    worker_enable_remote_control=False,
    # 关闭任务事件上报，降低监控事件流开销；如需实时监控（Flower）可开启
    worker_send_task_events=False,
    broker_heartbeat=10,
    broker_transport_options={"health_check_interval": 30},
)

# 默认队列名称的单一来源，供 worker 任务装饰器与生产者参考
DEFAULT_QUEUE_NAME = settings.WORKER_QUEUE_NAME



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
    celery_app.send_task(TASK_NAME_PROCESS_PDF, args=[task_id], queue=queue)
