import mineru.utils.config_reader as config_reader
from utils.selectGPU import GPUPool

def custom_get_device():
    gpu_pool = GPUPool()
    best_gpu = gpu_pool.get_best_gpu()
    
    if best_gpu is None:
        return "cpu"
    elif best_gpu.device_type == DeviceType.CUDA:
        return f"cuda:{best_gpu.index}"
    elif best_gpu.device_type == DeviceType.NPU:
        return f"npu:{best_gpu.index}"
    elif best_gpu.device_type == DeviceType.MPS:
        return "mps"
    else:
        return "cpu"
