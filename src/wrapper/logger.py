from functools import wraps
from loguru import logger
import time

def log_with_time_consumption(level="INFO"):
    """记录调用、返回、耗时、异常"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.log(level, f"调用 {func.__name__},参数：args={args},kwargs={kwargs}")
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log(level, f"{func.__name__} 返回：{result}，耗时：{duration:.3f}s")
                return result
            except Exception as e:
                logger.exception(f"{func.__name__} 执行异常：{e}")
                raise
        return wrapper
    return decorator


def log_function_call(level="INFO"):
    """记录调用、返回、异常"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.log(level, f"调用 {func.__name__}，参数：args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.log(level, f"{func.__name__} 返回：{result}")
                return result
            except Exception as e:
                logger.exception(f"{func.__name__} 执行异常：{e}")
                raise
        return wrapper
    return decorator


