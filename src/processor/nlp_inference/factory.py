from .interfaces import EmbeddingClient, NERClient
from .local_impl import LocalEmbeddingClient, LocalNERClient

class InferenceFactory:
    """
    Factory to create inference clients.
    Currently returns local clients, but can be extended to return remote clients based on configuration.
    使用工厂模式创建推理客户端
    目前返回本地客户端，但是可以根据配置返回远程客户端
    """
    @staticmethod
    def get_embedding_client() -> EmbeddingClient:
        return LocalEmbeddingClient()

    @staticmethod
    def get_ner_client() -> NERClient:
        return LocalNERClient()