from typing import Optional, Union, Any
import pickle
from .redis_client import RedisClient  # 只导入类
from utils.singleton import thread_safe_singleton

@thread_safe_singleton
class CacheService:
    def __init__(self):  # 直接使用类名
        self._client: Union[redis.Redis, EmbeddedRedis] = RedisClient().get_client()

    def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._client.set(key, value, ex=ex)

    def get(self, key: str) -> Union[Any, int, str, bytes, None]:
        raw = self._client.get(key)  # bytes or None
        if raw is None:
            return None
        # 判断是否是 pickle 存储的数据，例如以特殊前缀标识
        if raw.startswith(b'!'):
            return pickle.loads(raw[1:])
        else:
            # 尝试按数值解析
            try:
                text = raw.decode('utf-8')
                if text.isdigit():
                    return int(text)
                return text
            except UnicodeDecodeError:
                return raw  # 或者 raise 异常根据业务需求

    def delete(self, key: str) -> None:
        self._client.delete(key)


# 写一个测试代码
# 修改测试代码
# region
if __name__ == "__main__":
    # 直接创建 RedisClient 实例并传递给 CacheService
    # redis_client = RedisClient(mode='embedded')  # 使用嵌入式模式进行测试
    cache_service = CacheService()  # 手动传递实例
    
    cache_service.set("test", "test")
    print(cache_service.get("test"))
    cache_service.delete("test")
    print(cache_service.get("test"))
# endregion