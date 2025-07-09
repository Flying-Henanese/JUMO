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
from fastapi import UploadFile, File
from typing import List
# 为了让接口返回压缩包
import zipfile
from loguru import logger

from fastapi.responses import StreamingResponse
from io import BytesIO
import zipfile
from utils.selectGPU import GPUPool
from wrapper.gpu_patch import gpu_pool

# 实例化资源
router = APIRouter()
gpu_pool = GPUPool()
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

        if not task_repository.is_any_active_task() and gpu_pool.get_available_gpus():
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


@router.post("/upload-and-analyze-pdf/")
async def upload_and_analyze_pdf(
    background_tasks: BackgroundTasks,
    output_bucket: str,
    file: UploadFile = File(...),
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: OCRLanguage = OCRLanguage.get_default().value
):
    """
    上传并分析PDF文件的接口
    """
    try:
        # 检查output_bucket是否存在
        if not minio_tool.bucket_exists(output_bucket):
            raise HTTPException(status_code=400, detail=f"输出存储桶{output_bucket}不存在")
            
        # 生成唯一任务ID
        task_id = generate_short_uuid()
        
        # 上传文件到MinIO
        bucket_name = "uploads"  # 可以配置为常量
        object_name = f"{task_id}/{file.filename}"
        # 读取文件内容为字节流
        file_content = await file.read()
        # 获取文件类型（默认为application/octet-stream）
        content_type = file.content_type or "application/octet-stream"
        # 调用minio上传
        minio_tool.upload_file_by_bytes(
            bucket_name=bucket_name,
            object_name=object_name,
            file_bytes=file_content,
            content_type=content_type
        )

        # 创建任务
        task_to_add = Task(
            task_id=task_id,
            object_key=object_name,
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

        # 如果当前没有正在执行的任务并且有GPU资源
        if not task_repository.is_any_active_task() and gpu_pool.get_available_gpus():
            active_task.status = TaskStatus.PROCESSING
        elif task_repository.count_active_task() >= 20:
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
        raise HTTPException(status_code=500, detail=str(e))

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



@router.get("/download-task-files/{task_id}", response_class=StreamingResponse)
async def download_task_files(task_id: str):
    try:
        task = task_repository.get_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        if not task.output_info:
            raise HTTPException(status_code=400, detail="任务尚未完成")
        
        output_info = task.output_info

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_type, file_path in output_info.items():
                if file_type == 'images':
                    for img_path in file_path:
                        img_data = minio_tool.get_file_byte(
                            bucket_name=task.output_bucket,
                            object_name=img_path
                        )
                        zipf.writestr(img_path, img_data)
                else:
                    file_data = minio_tool.get_file_byte(
                        bucket_name=task.output_bucket,
                        object_name=file_path
                    )
                    zipf.writestr(file_path, file_data)

        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={task_id}_files.zip"}
        )
    except Exception as e:
        logger.error(f"下载任务文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.post("/reprocess-task/{task_id}")
async def reprocess_task(
    task_id: str,
    background_tasks: BackgroundTasks
):
    """
    重新处理指定任务
    :param task_id: 要重新处理的任务ID
    :return: 任务状态信息
    """
    try:
        # 获取原任务
        task = task_repository.get_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 检查任务是否已完成
        if task.finish_time is None:
            raise HTTPException(status_code=400, detail="任务尚未完成，无需重新处理")
        
        # 创建新的活跃任务
        active_task = ActiveTask(
            task_id=task_id,
            start_time=datetime.now(),
            queued_time=None,
            status=TaskStatus.QUEUED,
        )
        
        # 如果有可用GPU且无其他活跃任务，则直接开始处理
        if not task_repository.is_any_active_task() and gpu_pool.get_available_gpus():
            active_task.status = TaskStatus.PROCESSING
        elif task_repository.count_active_task() >= 20:
            raise HTTPException(status_code=429, detail="队列已满，请稍后再试")
        
        # 重置原任务状态（可选）
        task.finish_time = None
        task.output_info = ''
        task_repository.update_task(task)
        
        # 添加到活跃任务表
        active_task = task_repository.create_active_task(active_task)
        background_tasks.add_task(process_pdf_task, task)
        
        return JSONResponse(content={
            "task_id": task_id,
            "status": active_task.status,
            "message": "任务已加入队列" if active_task.status == TaskStatus.QUEUED else "任务正在处理"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重新处理失败: {str(e)}")


@router.post("/batch-task-status")
async def get_batch_task_status(task_ids: List[str]):
    """
    批量获取任务状态接口
    :param task_ids: 任务ID列表
    :return: 包含所有任务状态的列表
    """
    results = []
    
    for task_id in task_ids:
        active_task = task_repository.get_active_task(task_id)
        if active_task:
            results.append({
                "task_id": active_task.task_id,
                "status": active_task.status,
                "message": "任务正在处理" if active_task.status == TaskStatus.PROCESSING else "任务已加入队列"
            })
            continue
            
        task = task_repository.get_task_by_id(task_id)
        if task:
            results.append({
                "task_id": task.task_id,
                "status": TaskStatus.COMPLETED,
                "result": task.output_info
            })
        else:
            results.append({
                "task_id": task_id,
                "status": "not_found",
                "message": "任务不存在"
            })
    
    return JSONResponse(content=results)
        
