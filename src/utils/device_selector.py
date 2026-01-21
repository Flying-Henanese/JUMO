import os
from typing import Optional
from loguru import logger
import threading
import torch
from const.devices_enums import device_type_values
try:
    import torch_npu
    _HAS_TORCH_NPU = True
except Exception:
    _HAS_TORCH_NPU = False

_DEVICE_CACHE: Optional[str] = None
_LOCK = threading.Lock()

def _detect_device(preferred: Optional[str] = None) -> str:
    """
    设备检测核心逻辑：
    1. 优先使用函数传入的 preferred 参数
    2. 其次检查环境变量 DEVICE_MODE (cuda/npu/mps/cpu/auto)
    3. 最后尝试自动检测可用硬件 (cuda -> mps -> npu -> cpu)
    """
    
    # 1. 优先处理显式传入的 preferred
    if preferred:
        device_type = preferred.split(":")[0].lower()
        if device_type in device_type_values():
            return preferred
        logger.warning(f"传入的 preferred='{preferred}' 不合法，回退到后续检测逻辑")

    # 2. 检查环境变量 DEVICE_MODE
    env_mode = os.getenv("DEVICE_MODE", "auto").strip().lower().split(":")[0]
    if env_mode != "auto":
        if env_mode in device_type_values():
            return env_mode
        logger.warning(f"环境变量 DEVICE_MODE='{env_mode}' 不合法，回退到自动检测")

    # 3. 自动检测逻辑 (优先级: CUDA > MPS > NPU > CPU)
    try:
        if torch.cuda.is_available():
            logger.info("自动检测到 CUDA 设备，启用 GPU 加速")
            return "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            logger.info("自动检测到 MPS 设备，启用 Apple Silicon 加速")
            return "mps"
        elif _HAS_TORCH_NPU and torch.npu.is_available():
            logger.info("自动检测到 NPU 设备，启用华为昇腾加速")
            return "npu"
    except Exception as e:
        logger.warning(f"自动检测加速设备失败，回退到 CPU: {e}")

    # 4. 默认兜底
    logger.info("未检测到专用加速设备，使用 CPU 进行推理")
    return "cpu"

def get_device() -> str:
    global _DEVICE_CACHE
    if _DEVICE_CACHE is None:
        with _LOCK:
            if _DEVICE_CACHE is None:
                _DEVICE_CACHE = _detect_device(None)
    return _DEVICE_CACHE

def select_device(preferred: Optional[str] = None) -> str:
    if preferred:
        return _detect_device(preferred)
    return get_device()

