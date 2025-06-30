"""
pdf_route.py

定义 PDF 相关的接口路由，包括分析 PDF 接口和查询任务状态接口。
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
from minio.error import S3Error

from const.ocr_lang_enum import OCRLanguage
from data.model import Task, ActiveTask
from utils.id_generator import generate_short_uuid
from const.task_status_enum import TaskStatus
from processor.tasking.pdf_task import process_pdf_task
from startup import task_repository,minio_tool
# 实例化资源
router = APIRouter()

@router.post("/analyze-pdf/")
async def analyze_pdf(
    pdf_path: str, 
    background_tasks: BackgroundTasks, 
    bucket_name: str, 
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: OCRLanguage = OCRLanguage.get_default().value
):
    """
    分析PDF文件的接口
    """
    try:
        minio_tool.file_exists(bucket_name=bucket_name, object_name=pdf_path)
    except S3Error:
        raise HTTPException(status_code=404, detail="PDF文件未找到")

    task_id = generate_short_uuid()

    try:
        task_to_add = Task(
            task_id=task_id,
            object_key=pdf_path,
            bucket_name=bucket_name,
            output_bucket=output_bucket,
            ocr_enabled=ocr_enabled,
            table_enabled=table_enabled,
            ocr_lang=ocr_lang.value,
            output_info='',
            create_time=datetime.now(),
            finish_time=None,
        )

        active_task = ActiveTask(
            task_id=task_id,
            start_time=datetime.now(),
            queued_time=None,
            status=TaskStatus.QUEUED,
        )

        if not task_repository.is_any_active_task():
            active_task.status = TaskStatus.PROCESSING
        elif task_repository.count_active_task() >= 10:
            return JSONResponse(content={
                "task_id": "",
                "status": TaskStatus.FAILED,
                "message": "队列已满，请稍后再试"
            })

        task_repository.create_task(task_to_add)
        active_task = task_repository.create_active_task(active_task)
        background_tasks.add_task(process_pdf_task, task_to_add)

        return JSONResponse(content={
            "task_id": task_id,
            "status": active_task.status,
            "message": "任务已加入队列" if active_task.status == TaskStatus.QUEUED else "任务正在处理"
        })

    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态接口
    """
    active_task = task_repository.get_active_task(task_id)
    if active_task:
        return JSONResponse(content={
            "task_id": active_task.task_id,
            "status": active_task.status,
            "message": "任务正在处理" if active_task.status == TaskStatus.PROCESSING else "任务已加入队列"
        })

    task = task_repository.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return JSONResponse(content={
        "task_id": task.task_id,
        "status": TaskStatus.COMPLETED,
        "result": task.output_info
    })
