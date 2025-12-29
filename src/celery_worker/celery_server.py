"""
Celery 服务配置与核心模块

本模块主要负责：
1. 初始化 Celery 应用实例 (`celery_app`)，供生产者和消费者共同使用。
2. 配置 Celery 的各项参数，包括 Broker、Backend、序列化方式、时区、并发控制等。
3. 提供队列管理相关的工具函数，如查询队列长度 (`get_queue_length`)、选择负载最小的队列 (`choose_queue_by_least_backlog`)。
4. 提供统一的任务发送接口 (`send_pdf_task`)，屏蔽底层任务名称细节。

使用说明：
- 生产者（如 API 服务）：引用本模块的 `celery_app` 或 `send_pdf_task` 来分发任务。
- 消费者（Worker）：启动时加载本模块作为 Celery 的入口（app）。
"""
from celery import Celery
import os
from data.redis.redis_client import RedisClient
from utils.logging import setup_logger
setup_logger()
from loguru import logger
from celery_worker.celery_config import settings, build_redis_url, DEFAULT_QUEUE_NAME


# 模块常量：统一任务名
# 从环境变量中获取任务名，默认值为 "process_pdf"
# 这里为了保证和其他模块的任务名一致，所以这里也用环境变量来获取
# 这个任务名是为了指定在celery队列中这个任务的名称，生产者和消费者都要使用这个名称来发送和接收任务
TASK_NAME_PROCESS_PDF = os.getenv("TASK_NAME_PROCESS_PDF", "process_pdf")

broker_url = settings.CELERY_BROKER_URL or build_redis_url(settings.CELERY_REDIS_DB_BROKER)
result_backend = settings.CELERY_RESULT_BACKEND or build_redis_url(settings.CELERY_REDIS_DB_BACKEND)

# 这里的celery_app等于是一个celery的客户端实例
# 生产者和消费者都要引用这个模块来访问celery队列, 来发送任务或者接收任务
# 所以生产者和消费者都要import这个celery_server模块并引用这个celery_app实例
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

# 默认队列名称的单一来源，供生产者和消费者参考
DEFAULT_QUEUE_NAME = settings.WORKER_QUEUE_NAME

# 这个函数是给生产者用的，用来查询队列长度
# 这个模块上方的celery_app不会被重复实例化，因为路由部分的进程只有一个
def get_queue_length(queue_name: str) -> int:
    """
    查询 Redis broker 中某个 Celery 队列的等待任务数量（LLEN），并包含已预取但未确认的任务。
    """
    # 复用项目内的 RedisClient，显式使用 broker 的固定db=settings.CELERY_REDIS_DB_BROKER，避免每次调用都新建连接
    if not hasattr(get_queue_length, "_client"):
        get_queue_length._client = RedisClient(db_index=settings.CELERY_REDIS_DB_BROKER).get_client()
    # 这里的_client是一个简易的单例,等于是函数的一个隐式属性，函数首次调用后就会初始化这个属性
    # 因为我们这里在进程不会访问其他的redis实例以及db，所以这里可以安全地使用单例模式
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
    """
    从环境变量中解析 Celery 队列名称，支持逗号分隔。
    这里主要的目的是让外部获取到celery队列的名称，方便在不同的模块中使用
    """
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
