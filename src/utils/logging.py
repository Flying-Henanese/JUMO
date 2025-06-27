from loguru import logger
import os
import sys

def setup_logger(
    log_dir="logs",
    level="INFO",
    rotation="1 day",       # 每天新文件
    retention="7 days",     # 日志保留7天
    compression="zip"       # 自动压缩过期日志
):
    os.makedirs(log_dir, exist_ok=True)

    logger.remove()  # 移除默认的 stdout sink

    # 控制台 sink
    logger.add(sys.stderr, level=level, colorize=True, backtrace=True, diagnose=True)

    # 文件 sink
    logger.add(
        os.path.join(log_dir, "app_{time:YYYY-MM-DD}.log"),
        level=level,
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
        enqueue=True,   # 多进程安全
        serialize=False # 如果需要 JSON 日志可设 True
    )
