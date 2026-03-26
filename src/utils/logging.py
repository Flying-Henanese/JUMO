from loguru import logger
import os
import sys

import shutil

def setup_logger(
    log_dir="logs",
    level="INFO",
    rotation="1 day",       # 每天新文件
    retention="30 days",    # 日志保留30天
    compression="zip"       # 自动压缩过期日志
):
    history_dir = os.path.join(log_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    def compression_handler(log_file):
        """
        自定义压缩处理：压缩后将文件移动到 history 目录
        """
        # 1. 执行原有的压缩逻辑 (zip)
        zip_file = f"{log_file}.zip"
        import zipfile
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(log_file, os.path.basename(log_file))
        
        # 2. 将压缩后的文件移动到 history 目录
        target_path = os.path.join(history_dir, os.path.basename(zip_file))
        shutil.move(zip_file, target_path)
        
        # 3. 删除原始未压缩的日志文件
        os.remove(log_file)

    logger.remove()  # 移除默认的 stdout sink

    # 控制台 sink
    logger.add(sys.stderr, level=level, colorize=True, backtrace=True, diagnose=True)

    # 文件 sink
    logger.add(
        os.path.join(log_dir, "app_{time:YYYY-MM-DD}.log"),
        level=level,
        rotation=rotation,
        retention=retention,
        compression=compression_handler, # 使用自定义的清理/移动逻辑
        encoding="utf-8",
        enqueue=True,   # 多进程安全
        serialize=False # 如果需要 JSON 日志可设 True
    )
