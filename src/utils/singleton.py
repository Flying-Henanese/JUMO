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
    # 字典的设计允许 同一个装饰器 为 多个不同的类 分别实现单例模式
    # 如果使用单个变量，那么就只能为一个类实现单例模式
    # 其次，Python的类对象是可哈希的，可作为字典的键
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
    
    # 很有意思的一个点，这里返回的是 SingletonWrapper 类，而不是实例
    return SingletonWrapper


def parameterized_singleton(key_func=None):
    """
    参数化单例装饰器工厂函数
    基于参数创建不同的单例实例
    
    Args:
        key_func: 可选的函数，用于从参数中生成唯一键
                 如果为None，则使用所有参数的字符串表示作为键
    
    Returns:
        装饰器函数
    
    使用示例:
        @parameterized_singleton(lambda model_name: model_name)
        class MyModel:
            def __init__(self, model_name):
                self.model_name = model_name
        
        model1 = MyModel("model_a")  # 创建第一个实例
        model2 = MyModel("model_b")  # 创建第二个实例
    """
    def decorator(cls):
        import threading
        instances = {}
        lock = threading.Lock()
        
        class ParameterizedSingletonWrapper(cls):
            def __new__(cls_inner, *args, **kwargs):
                # 生成实例键
                if key_func:
                    try:
                        instance_key = key_func(*args, **kwargs)
                    except Exception:
                        # 如果key_func失败，回退到默认方法
                        instance_key = str(args) + str(sorted(kwargs.items()))
                else:
                    # 默认使用所有参数的字符串表示
                    instance_key = str(args) + str(sorted(kwargs.items()))
                
                with lock:
                    if instance_key not in instances:
                        instances[instance_key] = super(ParameterizedSingletonWrapper, cls_inner).__new__(cls_inner)
                        # 标记为新实例，需要初始化
                        instances[instance_key]._initialized = False
                    return instances[instance_key]
            
            def __init__(self, *args, **kwargs):
                # 检查是否已初始化
                if not getattr(self, '_initialized', False):
                    super(ParameterizedSingletonWrapper, self).__init__(*args, **kwargs)
                    self._initialized = True
        
        # 保持原类名和模块信息
        ParameterizedSingletonWrapper.__name__ = cls.__name__
        ParameterizedSingletonWrapper.__qualname__ = cls.__qualname__
        ParameterizedSingletonWrapper.__module__ = cls.__module__
        
        return ParameterizedSingletonWrapper

    # 很有意思的一个点，这里返回的是decorator函数，而不是实例
    # 因为Python装饰器等于是一个高阶函数，它接受一个函数作为参数，返回一个新的函数
    # 这里的高阶函数和数学中函数的概念是一样的，其实这个概念正式源自于数学中的high-order function
    return decorator