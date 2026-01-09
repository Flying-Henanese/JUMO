import ray
import os
from ray import serve
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from processor.nlp_inference.local_impl import LocalNERClient, LocalEmbeddingClient
from src.utils.auto_device_selector import get_env_vars_for_device

# Define request models
class ExtractRequest(BaseModel):
    '''
    NER实体识别的请求模型
    '''
    text: str
    confidence_threshold: float = 0.7
    return_objects: bool = False
    entity_num: int = 5

class EncodeRequest(BaseModel):
    '''
    文本嵌入向量计算的请求模型
    '''
    texts: List[str]

# Define FastAPI apps
ner_app = FastAPI()
embedding_app = FastAPI()

# Load device configuration
# inference_devices = os.getenv("INFERENCE_DEVICES", "0")
# Apply device visibility settings
# device_env = get_env_vars_for_device(inference_devices)
# for k, v in device_env.items():
#    os.environ[k] = v

# Get resource allocation from env
# Default to 0.2 GPUs per instance (assuming light NLP models)
nlp_gpu_per_instance = float(os.getenv("NLP_GPU_PER_INSTANCE", "0.1"))

@serve.deployment(
    ray_actor_options={"num_gpus": nlp_gpu_per_instance*2}, # NER模型要同时兼顾两种语言，所以比例稍大一点
    autoscaling_config={"min_replicas": 1, "max_replicas": 4}
)
@serve.ingress(ner_app)
class NERDeployment:
    def __init__(self):
        # 在 Actor 初始化时加载模型
        self.client = LocalNERClient()

    @ner_app.post("/extract")
    async def extract_api(self, request: ExtractRequest):
        return self.client.extract_entities(
            text=request.text,
            confidence_threshold=request.confidence_threshold,
            return_objects=False, # API always returns dicts for serialization
            entity_num=request.entity_num
        )

    def extract_entities(self, *args, **kwargs):
        return self.client.extract_entities(*args, **kwargs)

@serve.deployment(
    ray_actor_options={"num_gpus": nlp_gpu_per_instance},
    autoscaling_config={"min_replicas": 1, "max_replicas": 4}
)
@serve.ingress(embedding_app)
class EmbeddingDeployment:
    def __init__(self):
        self.client = LocalEmbeddingClient()

    @embedding_app.post("/encode")
    async def encode_api(self, request: EncodeRequest):
        results = self.client.encode(sentences=request.texts)
        
        # Handle numpy array
        if hasattr(results, "tolist"):
            return results.tolist()
            
        # Handle torch tensor (just in case)
        if hasattr(results, "cpu") and hasattr(results, "numpy"):
            return results.cpu().numpy().tolist()

        # Handle list of numpy objects
        if isinstance(results, list):
            import numpy as np
            if len(results) > 0 and isinstance(results[0], (np.ndarray, np.generic)):
                return [x.tolist() for x in results]
                
        return results

    def encode(self, *args, **kwargs):
        return self.client.encode(*args, **kwargs)

# 定义应用入口，方便通过 serve run 启动
# 实际部署时可能需要分别启动，或者组合在一起
ner_app = NERDeployment.bind()
embedding_app = EmbeddingDeployment.bind()