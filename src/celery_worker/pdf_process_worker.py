from loguru import logger
import os
from celery_worker.celery_config import settings  # 集中配置
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
# from processor.vlm_mode import PDFProcessor  # 移除顶层导入，避免父进程初始化 CUDA
from celery_worker.celery_server import celery_app, DEFAULT_QUEUE_NAME, TASK_NAME_PROCESS_PDF
from celery_worker.celery_config import parse_cuda_devices as _parse_cuda_devices
from data.operation import TaskRepository
from utils.minio_tool import MinioConnection
from data.model import Task
from const.task_status_enum import TaskStatus
import subprocess
from celery.signals import worker_process_init

# 每个 worker 通过环境变量指定自身设备与队列；未指定时默认取全局列表的第一个

_repo = None
_minio = None
_processor = None

@worker_process_init.connect
def _init_services(**kwargs):
    global _repo, _minio, _processor
    devices = _parse_cuda_devices()
    assigned = os.getenv("WORKER_GPU_DEVICE")
    device = assigned or (devices[0] if devices else None)
    if device:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(device)
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.set_device(0)
    except Exception:
        pass
    if _repo is None:
        _repo = TaskRepository()
    if _minio is None:
        _minio = MinioConnection()
    # 给mineru后端的合并列表和文本的函数添加猴子补丁，避免空值等问题
    if not globals().get("_patched"):
        try:
            from wrapper.merge_text import safe_merge_2_list_blocks, safe_merge_2_text_blocks
            import mineru.backend.pipeline.para_split as para_split
            para_split.__merge_2_list_blocks = safe_merge_2_list_blocks
            para_split.__merge_2_text_blocks = safe_merge_2_text_blocks
            from processor.converters.table_to_markdown import patch_batchanalyze_output_to_markdown
            patch_batchanalyze_output_to_markdown()
        except Exception:
            pass
        globals()["_patched"] = True
    if _processor is None:
        from processor.vlm_mode import PDFProcessor
        _processor = PDFProcessor(minio_tool=_minio, task_repository=_repo)

@celery_app.task(
    # 任务名：生产者侧会用send_task("process_pdf", ...)按此名称派发，需与注册名严格一致，所以这里使用预定义常量
    name=TASK_NAME_PROCESS_PDF, 
    # 绑定任务实例：允许在函数内通过 self 访问上下文（如 self.request、重试等）
    bind=True, 
    # 默认队列：任务若未显式指定 queue，将路由到该队列；生产者可用 send_task(queue=...) 覆盖
    queue=DEFAULT_QUEUE_NAME
)
def process_pdf_celery(self, task_id: str):
    """
    在独立的 Celery worker 进程中执行 PDF 处理任务。
    """
    # 使用进程级资源，必要时兜底懒加载
    global _repo, _minio, _processor
    if _repo is None or _minio is None or _processor is None:
        _init_services()

    repo = _repo
    processor = _processor

    # 标记开始处理
    try:
        repo.activate_task_by_id(task_id, status=TaskStatus.PROCESSING)
    except Exception as e:
        logger.error(f"activate_task_by_id 失败: {e}")

    # 获取 ORM Task 对象
    db = repo.SessionLocal()
    try:
        task_obj = db.query(Task).filter(Task.task_id == task_id).first()
        if task_obj is None:
            logger.error(f"Task {task_id} 不存在")
            return {"status": "not_found", "task_id": task_id}

        processor._sync_process_pdf(task_obj)
        logger.info(f"Task {task_id} 处理完成")
        succeeded = True
    except Exception as e:
        logger.exception(f"Task {task_id} 处理失败: {e}")
        succeeded = False
    finally:
        db.close()

    try:
        repo.complete_task(task_id, succeeded=succeeded)
    except Exception as e:
        logger.error(f"complete_task 失败: {e}")

    return {"status": "ok", "task_id": task_id}

# 自启动：按 CUDA_VISIBLE_DEVICES 自动生成多个 worker（每个设备一个）

if __name__ == "__main__":
    os.environ.setdefault('HF_ENDPOINT', settings.HF_ENDPOINT)
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', settings.CUDA_VISIBLE_DEVICES)
    # 不再硬编码 CUDA_VISIBLE_DEVICES，由部署环境注入
    devices = _parse_cuda_devices()
    if not devices:
        devices = [None]  # CPU 回退
    
    procs = []
    for idx, d in enumerate[str | None](devices):
        env = os.environ.copy()
        q = os.getenv("WORKER_QUEUE_NAME", DEFAULT_QUEUE_NAME)
        env["WORKER_QUEUE_NAME"] = q
        base_endpoint = os.getenv("VLLM_BASE_ENDPOINT", "localhost")
        base_port = int(os.getenv("VLLM_BASE_PORT", "8000"))
        env["VLLM_SERVER_URL"] = f"http://{base_endpoint}:{base_port + idx}/v1"
        if d is not None:
            env["WORKER_GPU_DEVICE"] = str(d)
            worker_name = f"worker_{q}_{d}@%h"
        else:
            worker_name = f"worker_{q}_cpu@%h"
        # Celery 应用模块路径（-A），用于定位任务与配置
        celery_app = "src.celery_worker.pdf_process_worker"
        # Worker 监听的队列名（-Q），决定消费哪个队列
        queue_name = DEFAULT_QUEUE_NAME
        # Worker 节点名称（-n），包含设备信息以保证唯一
        node_name = worker_name
        # 并发度（--concurrency），此处为 1 以避免资源争用
        concurrency = "1"
        # 池类型（-P），使用 solo 以允许任务内部安全地派生子进程
        pool_type = "solo"
        # 禁用 mingle：启动时不握手，降低事件开销
        without_mingle_flag = "--without-mingle"
        # 禁用 gossip：关闭集群状态广播，降低开销
        without_gossip_flag = "--without-gossip"
        # 禁用心跳：减少与 broker 的心跳检查带来的 CPU 负载
        without_heartbeat_flag = "--without-heartbeat"

        # 获取 celery 可执行文件路径，默认为 'celery'
        celery_bin = os.getenv("CELERY_PATH", "celery")

        cmd = [
            celery_bin,
            "-A", celery_app,
            "worker",
            "-Q", queue_name,
            "-n", node_name,
            "--concurrency", concurrency,
            "-P", pool_type,
            without_mingle_flag,
            without_gossip_flag,
            without_heartbeat_flag,
        ]
        procs.append(subprocess.Popen(cmd, env=env))
    for p in procs:
        p.wait()
