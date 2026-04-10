import os
import sys
import time
import json
import argparse
import glob
import pypdfium2 as pdfium
from datetime import datetime
from loguru import logger

# 将 src 目录加入 Python 路径，确保可以导入项目模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, 'src'))

# 导入项目内部模块
from startup import task_repository, minio_tool
from celery_worker.celery_server import celery_app, TASK_NAME_PROCESS_PDF, DEFAULT_QUEUE_NAME
from const.task_status_enum import TaskStatus
from data.model import Task
from utils.id_generator import generate_short_uuid

def run_bench(input_dir, output_dir, output_bucket, ocr_enabled=True):
    # 1. 扫描本地 PDF 文件
    files = glob.glob(os.path.join(input_dir, "*.pdf"))
    if not files:
        logger.error(f"在目录 {input_dir} 中未找到 PDF 文件")
        return

    logger.info(f"找到 {len(files)} 个文件准备处理...")
    
    upload_bucket = os.getenv('UPLOAD_BUCKET', 'uploads')
    task_ids = []
    total_pages = 0
    
    # 开始总计时
    bench_start_time = time.time()
    
    # 2. 准备阶段：上传并触发任务
    for fpath in files:
        fname = os.path.basename(fpath)
        
        # 计算页数
        try:
            pdf_doc = pdfium.PdfDocument(fpath)
            pages = len(pdf_doc)
            total_pages += pages
            pdf_doc.close()
        except Exception as e:
            logger.error(f"无法读取 PDF {fname} 的页数: {e}")
            pages = 0

        task_id = generate_short_uuid()
        # 存放在 bench/ 目录下方便清理
        object_key = f"bench/{task_id}/{fname}"
        
        logger.info(f"正在上传: {fname} (ID: {task_id})")
         #不用上传oss了，公网可能有比较大的延迟
        success = minio_tool.upload_file_by_path(
             bucket_name=upload_bucket,
             object_name=object_key,
             file_path=fpath
         )
        
            
        # 创建数据库记录（模拟 pdf_route.py 的逻辑）
        task = Task(
            task_id=task_id,
            bucket_name=upload_bucket,
            object_key=object_key,
            output_bucket=output_bucket,
            ocr_enabled=1 if ocr_enabled else 0,
            status=TaskStatus.QUEUED,
            create_time=datetime.now()
        )
        task_repository.create_task(task)
        task_ids.append(task_id)
        
        # 发送 Celery 任务
        celery_app.send_task(
            TASK_NAME_PROCESS_PDF, 
            args=[task_id], 
            queue=DEFAULT_QUEUE_NAME
        )
        logger.info(f"任务 {task_id} 已入队")

    # 3. 轮询监控阶段
    logger.info("所有任务已分发，开始监控状态...")
    
    total_count = len(task_ids)
    finished_tasks = {} # task_id -> task_obj
    
    while len(finished_tasks) < total_count:
        for tid in task_ids:
            if tid in finished_tasks:
                continue
                
            task = task_repository.get_task_by_id(tid)
            if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                finished_tasks[tid] = task
                status_str = "成功" if task.status == TaskStatus.COMPLETED else "失败"
                logger.info(f"任务 {tid} 已完成 ({status_str})。进度: {len(finished_tasks)}/{total_count}")
        
        if len(finished_tasks) < total_count:
            time.sleep(2) # 每 2 秒轮询一次
            
    bench_end_time = time.time()
    total_duration = bench_end_time - bench_start_time
    
    # 4. 结果下载与统计报告
    logger.info("=" * 50)
    logger.info(f"测试完成！总耗时: {total_duration:.2f} 秒")
    logger.info(f"总文件数: {total_count}")
    logger.info(f"总页数: {total_pages}")
    logger.info(f"平均处理速度 (按文件): {total_duration/total_count:.2f} 秒/文件")
    if total_pages > 0:
        logger.info(f"平均处理速度 (按页数): {total_duration/total_pages:.2f} 秒/页")
    logger.info("=" * 50)
    
    os.makedirs(output_dir, exist_ok=True)
    success_count = 0
    
    for tid, task in finished_tasks.items():
        if task.status == TaskStatus.COMPLETED:
            success_count += 1
    
    logger.info(f"成功回收 {success_count} 个任务的结果到 {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MinerU 本地性能测试脚本")
    parser.add_argument("--input", required=True, help="本地 PDF 输入目录")
    parser.add_argument("--output", required=True, help="本地结果保存目录")
    parser.add_argument("--bucket", default="output", help="OSS 输出存储桶名称 (默认: output)")
    parser.add_argument("--ocr", action="store_true", help="是否开启 OCR")
    
    args = parser.parse_args()
    
    # 确保输出目录是绝对路径
    abs_input = os.path.abspath(args.input)
    abs_output = os.path.abspath(args.output)
    
    run_bench(abs_input, abs_output, args.bucket, args.ocr)
