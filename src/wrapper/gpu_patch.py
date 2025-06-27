from magic_pdf.model.doc_analyze_by_custom_model import may_batch_image_analyze as original_may_batch
from functools import wraps

from utils.selectGPU import GPUPool
import os
import torch
from loguru import logger
from utils.selectGPU import GPUInfo

# 初始化GPU池
gpu_pool = GPUPool()

def patch_gpu_selection():
    """
    为may_batch_image_analyze添加GPU选择功能的装饰器
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            selected_gpu: GPUInfo = gpu_pool.get_best_gpu()
            if selected_gpu.device_type == 'cuda': # 只有在这个情况下才涉及选择最优GPU的问题
                if torch.cuda.is_available():
                    torch.cuda.set_device(selected_gpu.index)
                os.environ['CUDA_VISIBLE_DEVICES'] = str(selected_gpu.index)
                logger.info(f"Using CUDA GPU {selected_gpu.index}")
            else:
                logger.info(f"Using CPU/MPS/NPU")
            return func(*args, **kwargs)
        return wrapper

    import magic_pdf.model.doc_analyze_by_custom_model as module
    module.may_batch_image_analyze = decorator(original_may_batch)