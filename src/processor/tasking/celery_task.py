from celery import Celery
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'database', 'celery')
db_url = f"sqlite:///{db_path}"
app = Celery(
    'celery_task', 
    broker=f'sqla+{db_url}',
    backend=f'db+{db_url}'
    )





# poetry add redis-server
# from celery import Celery
# from redis_server import RedisServer
# import os
# import atexit

# # 启动嵌入式Redis服务器
# redis_server = RedisServer()
# redis_server.start()

# # 注册退出时关闭Redis
# atexit.register(redis_server.stop)

# app = Celery(
#     'celery_task', 
#     broker=f'redis://localhost:{redis_server.port}/0',
#     backend=f'redis://localhost:{redis_server.port}/1'
# )