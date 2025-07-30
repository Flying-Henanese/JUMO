# thread_pool_singleton.py
import os
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any

class _SingletonMeta(type):
    _instance = None
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__call__(*args, **kwargs)
        return cls._instance

class ThreadPoolSingleton(metaclass=_SingletonMeta):
    def __init__(self, max_workers: int | None = None):
        if not hasattr(self, "_initialized"):
            self._initialized = False
        if not self._initialized:
            # 线程数量不要太多，最多8个
            self._max_workers = max_workers or min(os.cpu_count()//2, 8)
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
            self._initialized = True
            self._shutdown_lock = threading.Lock()

    def submit(self, func: Callable[..., Any], *args, **kwargs) -> Future:
        return self._executor.submit(func, *args, **kwargs)

    def map(self, func: Callable[..., Any], iterable, chunksize: int = 1):
        return self._executor.map(func, iterable, chunksize=chunksize)

    def shutdown(self, wait: bool = True):
        with self._shutdown_lock:
            if self._executor:
                self._executor.shutdown(wait=wait)
                self._executor = None