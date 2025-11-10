from loguru import logger
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from processor.vlm_mode import PDFProcessor
from celery_worker.celery_server import celery_app
from data.operation import TaskRepository
from utils.minio_tool import MinioConnection
from data.model import Task
from const.task_status_enum import TaskStatus
import subprocess
from celery.signals import worker_process_init

def _parse_cuda_devices() -> list[str]:
    s = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p.strip() != ""]
    return parts

def _queue_name_for(device: str | None) -> str:
    return f"pdf_gpu{device}" if device else "pdf_cpu"

# 每个 worker 通过环境变量指定自身设备与队列；未指定时默认取全局列表的第一个
ASSIGNED_DEVICE = os.getenv("WORKER_GPU_DEVICE")
DEFAULT_QUEUE_NAME = os.getenv("WORKER_QUEUE_NAME", _queue_name_for(ASSIGNED_DEVICE))

_repo = None
_minio = None
_processor = None

@worker_process_init.connect
def _init_services(**kwargs):
    global _repo, _minio, _processor
    devices = _parse_cuda_devices()
    device = ASSIGNED_DEVICE or (devices[0] if devices else None)
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
    if _processor is None:
        _processor = PDFProcessor(minio_tool=_minio, task_repository=_repo)

@celery_app.task(name="process_pdf", bind=True, queue=DEFAULT_QUEUE_NAME)
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

    except Exception as e:
        logger.exception(f"Task {task_id} 处理失败: {e}")
    finally:
        db.close()

    # 完成当前任务并调度下一个
    try:
        next_task = repo.complete_task(task_id)
        if next_task:
            logger.info(f"从队列调度下一个任务: {next_task.task_id}")
            process_pdf_celery.delay(next_task.task_id)
        else:
            logger.info("队列为空，暂无下一个任务")
    except Exception as e:
        logger.error(f"complete_task 失败: {e}")

    return {"status": "ok", "task_id": task_id}

# 自启动：按 CUDA_VISIBLE_DEVICES 自动生成多个 worker（每个设备一个）
if __name__ == "__main__":
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
    devices = _parse_cuda_devices()
    if not devices:
        devices = [None]  # CPU 回退
    procs = []
    for d in devices:
        q = _queue_name_for(d)
        env = os.environ.copy()
        if d is not None:
            env["WORKER_GPU_DEVICE"] = str(d)
        env["WORKER_QUEUE_NAME"] = q
        cmd = [
            "celery", "-A", "src.celery_worker.pdf_process_worker", "worker",
            "-Q", q, "-n", f"worker_{q}@%h", "--concurrency", "1", "-P", "prefork",
        ]
        procs.append(subprocess.Popen(cmd, env=env))
    for p in procs:
        p.wait()
