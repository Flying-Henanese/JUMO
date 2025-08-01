"""
pdf_tasks.py

定义 PDF 分析的后台异步任务处理函数，负责将阻塞的 PDF 处理逻辑
放入线程池执行，并在任务完成后调度下一个排队的任务。

"""

import asyncio
from loguru import logger
from startup import task_repository, pdf_processor, thread_pool
from data.model import Task
from processor.vlm_mode import PDFProcessor


async def process_pdf_task(
    task_to_add: Task,
    pdf_processor_instance: PDFProcessor = pdf_processor
):
    """
    异步处理单个 PDF 任务，并在完成后自动调度下一个任务。

    :param task_to_add: 待处理的任务对象
    :param pdf_processor_instance: PDFProcessor 实例
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            thread_pool,
            pdf_processor_instance._sync_process_pdf,
            task_to_add
        )
        return result
    except Exception as e:
        logger.error(f"Error in process_pdf_task for {task_to_add.task_id}: {e}")
    finally:
        next_task = task_repository.complete_task(task_to_add.task_id)
        if next_task:
            logger.info(f"Task {next_task.task_id} started from queue.")
            asyncio.create_task(process_pdf_task(next_task))
        else:
            logger.info("No more tasks in queue.")
