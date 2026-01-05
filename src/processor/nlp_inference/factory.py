from .interfaces import EmbeddingClient, NERClient
from .local_impl import LocalEmbeddingClient, LocalNERClient
from .remote_impl import RemoteEmbeddingClient, RemoteNERClient
import os

class InferenceFactory:
    """
    Factory to create inference clients.
    now we offer two types of inference clients:
    1. local clients
    2. remote clients (based on Ray)
    使用工厂模式创建推理客户端
    支持:
    1. 本地的推理客户端
    2. 远程的推理客户端（基于 Ray）
    """
    @staticmethod
    def get_mode():
        return os.getenv("NLP_INFERENCE_MODE", "remote").lower() # 默认使用ray客户端

    @staticmethod
    def get_embedding_client() -> EmbeddingClient:
        if InferenceFactory.get_mode() in ["remote", "ray"]:
            return RemoteEmbeddingClient()
        return LocalEmbeddingClient()

    @staticmethod
    def get_ner_client() -> NERClient:
        if InferenceFactory.get_mode() in ["remote", "ray"]:
            return RemoteNERClient()
        return LocalNERClient()
