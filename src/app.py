from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
from startup import task_repository, minio_tool, pdf_processor, thread_pool
from data.model import Task, ActiveTask
from utils.id_generator import generate_short_uuid
import asyncio
from loguru import logger
import uvicorn
from minio.error import S3Error
from processor.pdf_processor import PDFProcessor
from const.task_status_enum import TaskStatus

app = FastAPI() # 启动服务


@app.post("/analyze-pdf/")
async def analyze_pdf(
    pdf_path: str, 
    background_tasks: BackgroundTasks, 
    bucket_name: str, 
    output_bucket: str,
    ocr_enabled: bool = False,
    table_enabled: bool = False,
    ocr_lang: str = "chi_sim",
    ):
    """
    分析PDF文件的接口

    :param pdf_path: PDF文件在MinIO中的路径
    :param background_tasks: 后台任务管理器，用于添加异步任务
    :param bucket_name: PDF文件所在的MinIO桶
    :param output_bucket: 分析结果输出的MinIO桶
    :param ocr_enabled: 是否开启OCR功能
    :param table_enabled: 是否开启表格识别功能
    :param ocr_lang: OCR识别语言
    :return: 任务ID
    """
    try:
        # 校验文件是否存在
        minio_tool.file_exists(bucket_name = bucket_name,object_name=pdf_path)
    except S3Error:
        raise HTTPException(status_code=404, detail="PDF文件未找到")
    task_id = generate_short_uuid()
    try:

        task_to_add = Task(
            task_id = task_id,
            object_key = pdf_path,
            bucket_name = bucket_name,
            output_bucket = output_bucket,
            ocr_enabled = ocr_enabled,
            table_enabled = table_enabled,
            ocr_lang = ocr_lang,
            output_info = '',
            create_time = datetime.now(),
            finish_time = None,
        )
        active_task = ActiveTask(
            task_id = task_id,
            start_time = datetime.now(),
            queued_time = None,
            status = TaskStatus.QUEUED,
        )

        # 如果没有正在执行的任务，那么就直接执行
        if not task_repository.is_any_active_task():
            active_task.status = TaskStatus.PROCESSING
        elif task_repository.count_active_task() >= 10:
            return JSONResponse(content={
                "task_id": "",
                "status": TaskStatus.FAILED,
                "message": "队列已满，请稍后再试"
            })
        # 任务信息和状态信息都入库
        task_repository.create_task(task_to_add)  # 直接传递SQLAlchemy对象
        active_task = task_repository.create_active_task(active_task)
        background_tasks.add_task(process_pdf_task,task_to_add)

        return JSONResponse(content={
            "task_id": task_id,
            "status": TaskStatus.QUEUED if active_task.status == TaskStatus.QUEUED else TaskStatus.PROCESSING,
            "message": "任务已加入队列" if active_task.status == TaskStatus.QUEUED else "任务正在处理"
        })
    except Exception as e:
        # 这里的异常类型有问题
        raise HTTPException(status_code=429, detail=str(e))

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    # task = tasks.get(task_id)
    active_task = task_repository.get_active_task(task_id)
    if active_task:
        return JSONResponse(content={
            "task_id": active_task.task_id,
            "status": active_task.status,
            "message": "任务正在处理" if active_task.status == TaskStatus.PROCESSING else "任务已加入队列"
        })
    task = task_repository.get_task_by_id(task_id)
    # task_output = TaskOut.model_validate(task, from_attributes=True)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return JSONResponse(content={
        "task_id": task.task_id,
        # "status": task.status,
        "result": task.output_info,
    })

async def process_pdf_task(
    task_to_add: Task,
    pdf_processor: PDFProcessor = pdf_processor
    ):
    '''
    异步处理PDF任务

    :param task_to_add: 待处理的任务对象
    :param pdf_processor: PDF处理器，用于实际处理PDF
    :return: 处理结果
    '''
    loop = asyncio.get_running_loop()
    try:
        # 将同步阻塞函数放到线程池中执行
        result = await loop.run_in_executor(
            thread_pool,
            pdf_processor._sync_process_pdf,  # 使用PDFProcessor的方法
            task_to_add
        )
        return result
    except Exception as e:
        # 错误处理已经在_sync_process_pdf内部完成，这里只是为了捕获未处理的异常
        print(f"Error in process_pdf_task for {task_to_add.task_id}: {e}")
    finally:
        # 任务完成后，从任务池中移除任务，并获取下一个任务ID
        next_task = task_repository.complete_task(task_to_add.task_id)
        # 关键：在这里使用 asyncio.create_task 或 BackgroundTasks 调度下一个任务
        # 因为 process_pdf_task 运行在主事件循环中，可以安全地调度异步任务
        # 注意：这里直接使用 asyncio.create_task 更符合内部调度，
        # 如果想让FastAPI管理，也可以考虑重新调用 analyze_pdf 接口
        # 但内部调度更合适，避免了HTTP请求的开销
        if next_task:
            asyncio.create_task(process_pdf_task(next_task))
            print(f"Task {next_task.task_id} started from queue.")
        else:
            print("No more tasks in queue.")

if __name__ == "__main__":
    logger.info("启动FastAPI服务，监听端口8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)