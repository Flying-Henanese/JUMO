# import torch
# from mineru.utils import block_sort
# import os
# """
# 暂不启用这个吧，潜在问题还很多
# """
# # 保存原始函数
# _original_model_init = block_sort.model_init
# device_type = os.getenv('MINERU_DEVICE_TYPE')
# # 补丁函数
# def patched_model_init(*args, **kwargs):
#     model = _original_model_init(*args, **kwargs)

#     # 判断模型是否是 meta tensor
#     if any(p.device.type == "meta" for p in model.parameters()):
#         print("🛠️ [patch] meta tensor detected, using to_empty()")
#         model = model.to_empty(device_type) 
#     else:
#         model = model.to(device_type)  # 替换成你的目标设备

#     return model.eval().bfloat16()  # 保持原来的后续调用

