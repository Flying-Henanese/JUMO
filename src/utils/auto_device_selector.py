import os
from typing import Optional
from loguru import logger
import threading
import torch

try:
    import torch_npu
    _HAS_TORCH_NPU = True
except ImportError:
    _HAS_TORCH_NPU = False

_DEVICE_CACHE: Optional[str] = None
_LOCK = threading.Lock()

def _detect_hardware() -> str:
    """
    自动检测底层硬件并返回统一的设备字符串。
    策略：
    1. 已经通过环境变量（如 CUDA_VISIBLE_DEVICES）实现了进程级隔离，
       因此每个进程看到的都是"私有"的设备，统一使用索引 0。
    2. 检测顺序：CUDA -> NPU -> MPS -> CPU。
    """
    
    # 1. Detect CUDA (NVIDIA GPUs)
    if torch.cuda.is_available():
        # 获取可见设备的数量，用于日志记录
        device_count = torch.cuda.device_count()
        logger.info(f"Auto-detected CUDA. Visible devices: {device_count}. Using 'cuda:0'.")
        return "cuda:0"

    # 2. Detect NPU (Huawei Ascend)
    if _HAS_TORCH_NPU and torch.npu.is_available():
        # 获取可见设备的数量，用于日志记录
        device_count = torch.npu.device_count()
        logger.info(f"Auto-detected NPU. Visible devices: {device_count}. Using 'npu:0'.")
        return "npu:0"

    # 3. Detect MPS (Apple Silicon)
    # MPS 目前通常作为单设备处理，不强调索引
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        logger.info("Auto-detected MPS (Apple Silicon). Using 'mps'.")
        return "mps"

    # 4. Fallback to CPU
    logger.info("No hardware accelerator detected. Using 'cpu'.")
    return "cpu"

def get_device() -> str:
    """
    获取当前环境的最佳计算设备。
    返回示例: 'cuda:0', 'npu:0', 'mps', 'cpu'
    备注：默认选择第一个可见设备的原因是给每个进程分配一个课件设备，所以无脑选择type:0是遵循我的设计逻辑的
    """
    global _DEVICE_CACHE
    if _DEVICE_CACHE is None:
        with _LOCK:
            if _DEVICE_CACHE is None:
                _DEVICE_CACHE = _detect_hardware()
    return _DEVICE_CACHE

def get_device_type() -> str:
    """
    获取设备类型（不带索引）。
    返回示例: 'cuda', 'npu', 'mps', 'cpu'
    """
    device = get_device()
    return device.split(":")[0]

def get_env_vars_for_device(device_id: str) -> dict[str, str]:
    """
    根据自动检测到的硬件类型，构造用于隔离设备的进程环境变量。

    Args:
        device_id: 具体的设备ID（例如 "0", "1", "0,1"）

    Returns:
        - CUDA: {"CUDA_VISIBLE_DEVICES": device_id}
        - NPU:  {"ASCEND_RT_VISIBLE_DEVICES": device_id}
        - MPS/CPU: {} (无需/无法隔离)
    """
    device_type = get_device_type()

    if device_type == "cuda":
        return {"CUDA_VISIBLE_DEVICES": device_id}
    if device_type == "npu":
        return {"ASCEND_RT_VISIBLE_DEVICES": device_id}

    return {}

def get_env_kv_string_for_device(device_id: str) -> str:
    """
    将 get_env_vars_for_device 的结果转换为 shell 友好的 KEY=VALUE 字符串。
    """
    env_vars = get_env_vars_for_device(device_id)
    if not env_vars:
        return ""
    k, v = next(iter(env_vars.items()))
    return f"{k}={v}"


