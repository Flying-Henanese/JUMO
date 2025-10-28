def singleton(cls):
    """单例装饰器（已弃用，建议使用 class_singleton）"""
    instances = {}
    
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance


def thread_safe_singleton(cls):
    """线程安全的单例装饰器（已弃用，建议使用 class_singleton）"""
    import threading
    instances = {}
    lock = threading.Lock()
    
    def get_instance(*args, **kwargs):
        with lock:
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
            return instances[cls]
    
    return get_instance


def class_singleton(cls):
    """
    改进的线程安全单例装饰器
    保持类的类型不变，支持 super()、isinstance() 等类特性
    """
    import threading
    instances = {}
    lock = threading.Lock()

    class SingletonWrapper(cls):
        _initialized = False

        def __new__(cls_inner, *args, **kwargs):
            with lock:
                if cls_inner not in instances:
                    instances[cls_inner] = super(SingletonWrapper, cls_inner).__new__(cls_inner)
            return instances[cls_inner]

        def __init__(self, *args, **kwargs):
            # 确保 __init__ 只执行一次
            if not self._initialized:
                super(SingletonWrapper, self).__init__(*args, **kwargs)
                self._initialized = True

    # 保持原类名和模块信息
    SingletonWrapper.__name__ = cls.__name__
    SingletonWrapper.__qualname__ = cls.__qualname__
    SingletonWrapper.__module__ = cls.__module__
    
    return SingletonWrapper