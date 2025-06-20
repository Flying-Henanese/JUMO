from magic_pdf.model.doc_analyze_by_custom_model import may_batch_image_analyze as original_may_batch
from functools import wraps

from torch.cpu import is_available
from utils.selectGPU import GPUPool
import os
import torch

# 初始化GPU池
gpu_pool = GPUPool()

def patch_gpu_selection():
    """
    为may_batch_image_analyze添加GPU选择功能的装饰器
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            gpu_id = gpu_pool.get_best_gpu()
            if gpu_id is not None:
                if torch.cuda.is_available():
                    torch.cuda.set_device(gpu_id)
                os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
            return func(*args, **kwargs)
        return wrapper

    import magic_pdf.model.doc_analyze_by_custom_model as module
    module.may_batch_image_analyze = decorator(original_may_batch)