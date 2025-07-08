from functools import wraps
import torch
import os
from loguru import logger
from const.devices_enums import DeviceType
from utils.selectGPU import GPUPool, GPUInfo

gpu_pool = GPUPool()

def with_gpu_selection(func):
    """
    装饰器：自动选择可用 GPU，并设置 CUDA_VISIBLE_DEVICES
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        selected_gpu: GPUInfo = gpu_pool.get_best_gpu()
        if selected_gpu.device_type == DeviceType.CUDA and torch.cuda.is_available():
            os.environ['CUDA_VISIBLE_DEVICES'] = str(selected_gpu.index)
            logger.info(f"Using CUDA GPU {selected_gpu.index}")
        elif selected_gpu.device_type == 'NPU':
            # 这里还要在确认一下，暂时还没有找到指定NPU的环境变量
            os.environ['MINERU_NPU_DEVICES'] = str(selected_gpu.index)
            logger.info(f'Using NPU {selected_gpu.index}')
        elif selected_gpu.device_type == DeviceType.MPS:
            logger.info(f'Using MPS {selected_gpu.index}')
        else:
            logger.info("Using CPU")
        return func(*args, **kwargs)
    return wrapper
