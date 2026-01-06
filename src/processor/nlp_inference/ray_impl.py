'''
未使用状态
这个模块实现了通过 Ray Serve的remote procedure call (RPC) 调用 NER 和 Embedding 服务。
但是现在没有实际使用，而是和mineru模型一样使用http client方式进行调用
'''
from typing import List, Union, Dict, Any
import numpy as np
from ray import serve
from .interfaces import NERClient, EmbeddingClient

class RayNERClient(NERClient):
    """
    Client that connects to the remote Ray Serve NER deployment.
    """
    def __init__(self, app_name: str = "default"):
        # 获取远程部署的句柄
        # 注意：这里假设应用名称是 "default" 或者你在 serve run 时指定的名称
        # 如果是同个脚本启动，通常可以通过 serve.get_deployment("NERDeployment").get_handle()
        self.handle = serve.get_deployment("NERDeployment").get_handle()

    def extract_entities(self, 
                        text: str, 
                        confidence_threshold: float = 0.7, 
                        return_objects: bool = False, 
                        entity_num: int = 5) -> List[Union[Dict[str, Any], Any]]:
        # 远程调用
        return self.handle.extract_entities.remote(
            text=text,
            confidence_threshold=confidence_threshold,
            return_objects=return_objects,
            entity_num=entity_num
        ).result()

class RayEmbeddingClient(EmbeddingClient):
    """
    Client that connects to the remote Ray Serve Embedding deployment.
    """
    def __init__(self, app_name: str = "default"):
        self.handle = serve.get_deployment("EmbeddingDeployment").get_handle()

    def encode(self, sentences: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]], np.ndarray]:
        return self.handle.encode.remote(sentences, **kwargs).result()