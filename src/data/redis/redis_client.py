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
        
        # 如果使用内嵌redis服务
        if os.getenv('USE_INDEPENDENT_REDIS', '').lower() == "false":
            # 这里有点像是一个monkey patch，把redis标准的客户端重定向到内嵌的redis客户端
            # 这样我们就可以不改变使用方式，同时使用内嵌的redis服务了
            rpatch.patch_redis(dbfile=embedded_dbfile)
            # 这里设置decode_responses=False，因为我们需要原始的字节数据，后续使用pickle进行反序列化
            self.client = EmbeddedRedis(dbfilename=embedded_dbfile, decode_responses=False) if embedded_dbfile else EmbeddedRedis()
            # 对于内嵌Redis，使用SELECT命令切换数据库
            self.client.execute_command('SELECT', self.db)
        # 如果使用外部独立redis服务
        else:
            # 这里需要unpatch，因为如果之前使用了内嵌的redis服务，那么这里需要把连接重定向到外部的redis服务
            # 虽然这里和上面的分支是互斥的，但作为防御性措施，防止出现问题
            rpatch.unpatch_redis()
            # 使用环境变量配置连接外部redis服务
            cfg = external_config or (get_redis_config_from_env() or {})
            if db_index is not None:
                cfg['db'] = db_index
            pool = redis.ConnectionPool(**cfg)
            self.client = redis.Redis(connection_pool=pool, decode_responses=False)

    def get_client(self) -> Union[redis.Redis, EmbeddedRedis]:
        return self.client

# 移除 get_redis_client 函数，直接使用 RedisClient 类