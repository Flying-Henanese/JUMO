"""
pdf_route.py

定义 PDF 相关的接口路由，包括分析 PDF 接口和查询任务状态接口。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from minio.error import S3Error
from const.ocr_lang_enum import OCRLanguage
from data.model import Task
from utils.id_generator import generate_short_uuid
from const.task_status_enum import TaskStatus
from startup import task_repository,minio_tool
from fastapi import UploadFile, File
from typing import List
# 为了让接口返回压缩包
import zipfile
from loguru import logger
import os
from fastapi.responses import StreamingResponse
from io import BytesIO
import zipfile
from celery_worker.celery_server import DEFAULT_QUEUE_NAME, get_queue_length, send_pdf_task
from const.file_extensions import OFFICE_EXTENSIONS, PDF_EXTENSIONS, IMAGE_EXTENSIONS,EXCEL_EXTENTIONS

# 实例化资源
router = APIRouter()
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 8))
MAX_QUEUING_TASKS = int(os.getenv('MAX_QUEUING_TASKS', 40))
UPLOAD_BUCKET = os.getenv('UPLOAD_BUCKET', 'uploads')

@router.post("/drop-pdf")
def drop_pdf(
    pdf_path: str,
    bucket_name: str,
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    formula_enabled: bool = False,
    inline_formula_enabled: bool = True,
    ocr_lang: OCRLanguage = OCRLanguage.get_default()
):
    """
    将 pdf_path 视为 MinIO 前缀（目录），遍历其中所有对象并为每个对象创建任务。
    若前缀为空但 pdf_path 指向单个对象存在，则仅为该对象创建任务。
    """
    try:
        objects = minio_tool.list_objects(bucket_name=bucket_name, prefix=pdf_path, recursive=True)
        if not objects:
            if not minio_tool.file_exists(bucket_name=bucket_name, object_name=pdf_path):
                raise HTTPException(status_code=404, detail="路径下没有文件或文件不存在")
            objects = [pdf_path]

        # 因为minio中可能会有目录作为文件存在，所有需要过滤掉目录和不支持的文件类型
        # 并且也对重复的文件进行去重
        allowed_exts = {*PDF_EXTENSIONS, *IMAGE_EXTENSIONS, *OFFICE_EXTENSIONS,*EXCEL_EXTENTIONS}
        objects = [obj for obj in objects if not obj.endswith('/') and os.path.splitext(obj)[-1].lower() in allowed_exts]
        objects = sorted(set(objects))
        if not objects:
            raise HTTPException(status_code=404, detail="路径下没有可处理的文件")

        target_queue = DEFAULT_QUEUE_NAME
        backlog = get_queue_length(target_queue)
        if backlog >= MAX_QUEUING_TASKS:
            return JSONResponse(content={
                "task_id": "",
                "status": TaskStatus.QUEUED,
                "message": f"队列压力过大({target_queue}:{backlog})，请稍后重试"
            }, status_code=429)

        task_ids = []
        for obj in objects:
            task_id = generate_short_uuid()
            task_to_add = Task(
                task_id=task_id,
                object_key=obj,
                bucket_name=bucket_name,
                output_bucket=output_bucket,
                ocr_enabled=ocr_enabled,
                table_enabled=table_enabled,
                formula_enabled=formula_enabled,
                inline_formula_enabled=inline_formula_enabled,
                ocr_lang=ocr_lang.value,
                output_info='',
                create_time=datetime.now(),
                finish_time=None,
                status=TaskStatus.QUEUED,
            )
            task_repository.create_task(task_to_add)
            send_pdf_task(task_id, target_queue)
            task_ids.append(task_id)

        logger.info(f"路径 {pdf_path} 下共 {len(objects)} 个文件已入队到 {target_queue}，当前等待数: {backlog}")
        return JSONResponse(content={
            "task_ids": task_ids,
            "status": TaskStatus.QUEUED,
            "message": f"已创建 {len(task_ids)} 个任务",
            "queue": target_queue,
            "backlog": backlog,
            "count": len(task_ids)
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"任务入队失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")


@router.post("/analyze-pdf")
def analyze_pdf(
    pdf_path: str, 
    bucket_name: str, 
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    formula_enabled: bool = False,
    inline_formula_enabled: bool = True,
    ocr_lang: OCRLanguage = OCRLanguage.get_default()
):
    """
    分析PDF文件的接口（移除 ActiveTask 引用，保留本地 BackgroundTasks）
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
            formula_enabled=formula_enabled,
            inline_formula_enabled=inline_formula_enabled,
            ocr_lang=ocr_lang.value,
            output_info='',
            create_time=datetime.now(),
            finish_time=None,
            status=TaskStatus.QUEUED,
        )


        if task_repository.count_active_task() >= MAX_QUEUING_TASKS:
            return JSONResponse(content={
                "task_id": "",
                "status": TaskStatus.FAILED,
                "message": "队列已满，请稍后再试"
            })

        task_repository.create_task(task_to_add)
        send_pdf_task(task_id, DEFAULT_QUEUE_NAME)

        return JSONResponse(content={
            "task_id": task_id,
            "status": TaskStatus.QUEUED,
            "message": "任务已加入队列"
        })

    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.post("/upload-and-analyze-pdf")
def upload_and_analyze_pdf(
    output_bucket: str,
    file: UploadFile = File(...),
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    formula_enabled: bool = False,
    inline_formula_enabled: bool = True,
    ocr_lang: OCRLanguage = OCRLanguage.get_default()
):
    """
    上传并分析PDF文件（移除 ActiveTask 引用，保留本地 BackgroundTasks）
    """
    try:
        # 检查output_bucket是否存在
        if not minio_tool.bucket_exists(output_bucket):
            raise HTTPException(status_code=400, detail=f"输出存储桶{output_bucket}不存在")
            
        # 生成唯一任务ID
        task_id = generate_short_uuid()
        
        # 上传文件到MinIO
        bucket_name = UPLOAD_BUCKET  # 可以配置为常量
        object_name = f"{task_id}/{file.filename}"
        # 读取文件内容为字节流
        file_content = file.file.read()
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
            formula_enabled=formula_enabled,
            inline_formula_enabled=inline_formula_enabled,
            ocr_lang=ocr_lang.value,
            output_info='',
            create_time=datetime.now(),
            finish_time=None,
            status=TaskStatus.QUEUED,
        )

        if task_repository.count_active_task() >= MAX_QUEUING_TASKS:
            return JSONResponse(content={
                "task_id": "",
                "status": TaskStatus.FAILED,
                "message": "队列已满，请稍后再试"
            })

        task_repository.create_task(task_to_add)
        send_pdf_task(task_id, DEFAULT_QUEUE_NAME)

        return JSONResponse(content={
            "task_id": task_id,
            "status": TaskStatus.QUEUED,
            "message": "任务已加入队列"
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/task-status/{task_id}")
def get_task_status(task_id: str):
    """
    获取任务状态接口（不再依赖 ActiveTask）
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
        "status": task.status,
        "result": task.output_info if task.status == TaskStatus.COMPLETED else None
    })

@router.get("/download-task-files/{task_id}", response_class=StreamingResponse)
def download_task_files(task_id: str):
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
def reprocess_task(
    task_id: str
):
    """
    重新处理指定任务（移除 ActiveTask，改为 Celery 入队）
    """
    try:
        # 获取原任务
        task: Task = task_repository.get_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 检查任务是否已完成
        if task.finish_time is None:
            raise HTTPException(status_code=400, detail="任务尚未完成，无需重新处理")
        # 把任务放到celery队列中
        send_pdf_task(task_id, DEFAULT_QUEUE_NAME)
        
        # 重置原任务状态（可选）
        task.finish_time = None
        task.output_info = ''
        task_repository.update_task(task)
        # 这里直接返回加入队列
        # 尽管当前任务可能正在处理中
        return JSONResponse(content={
            "task_id": task_id,
            "status": TaskStatus.QUEUED,
            "message": "任务已加入队列"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重新处理失败: {str(e)}")


@router.post("/batch-task-status")
def get_batch_task_status(task_ids: List[str]):
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
        
