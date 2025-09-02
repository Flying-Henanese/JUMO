# redis_client.py
from typing import Union
import redis
import redislite.patch as rpatch
from redislite import Redis as EmbeddedRedis
from utils.singleton import thread_safe_singleton

@thread_safe_singleton
class RedisClient:
    def __init__(
        self,
        mode: str = 'embedded',
        external_config: dict = None,
        embedded_dbfile: str = None,
    ):
        self.mode = mode
        if mode == 'embedded':
            rpatch.patch_redis(dbfile=embedded_dbfile)
            self.client = EmbeddedRedis(dbfilename=embedded_dbfile, decode_responses=False) if embedded_dbfile else EmbeddedRedis()
        else:
            rpatch.unpatch_redis()
            pool = redis.ConnectionPool(**(external_config or {}))
            self.client = redis.Redis(connection_pool=pool, decode_responses=False)

    def get_client(self) -> Union[redis.Redis, EmbeddedRedis]:
        return self.client

# 移除 get_redis_client 函数，直接使用 RedisClient 类

