import pytest

from data.redis.cache_service import CacheService

def test_redis_cache(capsys):  # 添加 capsys 参数
    cache_service = CacheService()
    print("") 
    cache_service.set("test", "test")
    result = cache_service.get("test")
    print(result)  # 这个输出会被捕获
    
    cache_service.delete("test")
    result = cache_service.get("test")
    print(result)  # 这个输出也会被捕获
    captured = capsys.readouterr()
    
    # 手动打印你关心的内容
    print("\n=== Debug Output ===")
    print(captured.out)