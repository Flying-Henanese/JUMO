from functools import wraps
import torch
import os
from loguru import logger
from utils.selectGPU import GPUPool, GPUInfo

gpu_pool = GPUPool()

def with_gpu_selection(func):
    """
    装饰器：自动选择可用 GPU，并设置 CUDA_VISIBLE_DEVICES
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        selected_gpu: GPUInfo = gpu_pool.get_best_gpu()
        if selected_gpu.device_type == 'cuda' and torch.cuda.is_available():
            # 按照pytorch官方的建议，优先使用cuda_visible_devices
            # torch.cuda.set_device(selected_gpu.index)
            os.environ['CUDA_VISIBLE_DEVICES'] = str(selected_gpu.index)
            logger.info(f"Using CUDA GPU {selected_gpu.index}")
        else:
            logger.info("Using CPU/NPU/MPS")
        return func(*args, **kwargs)
    return wrapper
