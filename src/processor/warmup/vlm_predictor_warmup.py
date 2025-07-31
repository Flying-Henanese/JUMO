# predictor_setup.py
from mineru.backend.vlm.predictor import get_predictor
import os

predictor = get_predictor(
    backend="sglang-engine",
    model_path=os.path.expanduser("~/.cache/modelscope/hub/models/OpenDataLab/MinerU2.0-2505-0.9B"),  # 使用默认路径或你的自定义路径
    server_url=None,
    max_new_tokens=32,      # 小量 token 以觸运行逻辑
    # 其他你通常传入的 kwargs
)
