# redis_client.py
from typing import Union
import redis
import redislite.patch as rpatch
from redislite import Redis as EmbeddedRedis
from utils.singleton import parameterized_singleton
import const.redis_constants as redis_constants
import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

def get_redis_config_from_env():
    """从环境变量读取Redis配置"""
    return {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', 6379)),
        'db': int(os.getenv('REDIS_DB', 0)), # 配置redis_db编号，从0到
        'password': os.getenv('REDIS_PASSWORD') or None,  # 空字符串转为None
        'decode_responses': False
    }

@parameterized_singleton()
class RedisClient:
    def __init__(
        self,
        mode: str = redis_constants.REDIS_MODE_EMBEDDED,
        external_config: dict = None,
        embedded_dbfile: str = None,
        db_index: int = None,
    ):
        self.mode = mode
        self.db = db_index if db_index is not None else int(os.getenv('REDIS_DB', 0))
        
        # 使用环境变量配置连接外部redis服务
        cfg = external_config or (get_redis_config_from_env() or {})
        if db_index is not None:
            cfg['db'] = db_index
        pool = redis.ConnectionPool(**cfg)
        self.client = redis.Redis(connection_pool=pool, decode_responses=False)

    def get_client(self) -> Union[redis.Redis, EmbeddedRedis]:
        return self.client

# 移除 get_redis_client 函数，直接使用 RedisClient 类