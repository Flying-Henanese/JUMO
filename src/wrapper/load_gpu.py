import mineru.utils.config_reader as config_reader
from utils.selectGPU import GPUPool
from loguru import logger

def custom_get_device():
    gpu_pool = GPUPool()
    best_gpu = gpu_pool.get_best_gpu()
    
    if best_gpu is None:
        return "cpu"
    elif best_gpu.device_type == DeviceType.CUDA:
        logger.info(f"CUDA GPU {best_gpu.index} with {best_gpu.free_mem_str} memory available")
        return f"cuda:{best_gpu.index}"
    elif best_gpu.device_type == DeviceType.NPU:
        logger.info(f"NPU {best_gpu.index} with {best_gpu.free_mem_str} memory available")
        return f"npu:{best_gpu.index}"
    elif best_gpu.device_type == DeviceType.MPS:
        logger.info(f"MPS with {best_gpu.free_mem_str} memory available")
        return "mps"
    else:
        logger.info(f"CPU with {best_gpu.free_mem_str} memory available")
        return "cpu"
