"""
API身份验证装饰器模块

提供基于API-KEY的身份验证装饰器，用于保护FastAPI接口
"""

from functools import wraps
from typing import Optional, List, Callable, Any
from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
import os
import logging

# 配置日志
logger = logging.getLogger(__name__)

# 从环境变量获取api-keys的值，多个key用逗号分隔
API_KEYS = os.getenv('API_KEYS', '').split(',') if os.getenv('API_KEYS') else []
API_KEY = os.getenv('API_KEY', 'API-KEY')
REQUIRE_API_KEY = os.getenv('REQUIRE_API_KEY', 'false').lower() == 'true'

# 移除空字符串
API_KEYS = [key.strip() for key in API_KEYS if key.strip()]

def validate_api_key(api_key: str) -> bool:
    """
    验证API Key的有效性
    
    Args:
        api_key: 待验证的API Key
        
    Returns:
        bool: 是否验证通过
    """
    if not API_KEYS:
        # 如果没有配置API Keys，根据REQUIRE_API_KEY决定是否要求认证
        return not REQUIRE_API_KEY
    
    return api_key in API_KEYS

def api_key_required(
    required: bool = True,
    scopes: Optional[List[str]] = None
) -> Callable:
    """
    API Key认证装饰器
    
    Args:
        required: 是否必须提供API Key
        scopes: 需要的权限范围（预留功能）
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 从请求中获取API Key
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break
            
            api_key = None
            if request:
                api_key = request.headers.get(API_KEY)
            
            # 如果没有提供API Key且认证是必须的
            if not api_key and required:
                logger.warning(f"Missing API Key in header: {API_KEY}")
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail=f"API Key required. Please provide '{API_KEY}' header"   
                )
            
            # 验证API Key
            if api_key and not validate_api_key(api_key):
                logger.warning(f"Invalid API Key provided: {api_key}")
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail="Invalid API Key"
                )
            
            # 如果没有API Key但认证不是必须的，或者认证通过
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def require_api_key(func: Callable) -> Callable:
    """
    简化的API Key认证装饰器（必须提供有效的API Key）
    """
    return api_key_required(required=True)(func)

def optional_api_key(func: Callable) -> Callable:
    """
    可选的API Key认证装饰器（有API Key时验证，没有时也允许访问）
    """
    return api_key_required(required=False)(func)

# 导出主要功能
__all__ = [
    'api_key_required',
    'require_api_key', 
    'optional_api_key',
    'validate_api_key'
]