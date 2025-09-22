"""
响应工具模块 - 提供统一的API响应格式和工具函数
"""

from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, Field
from const.http_status_codes import HttpStatusCode, STATUS_MESSAGES, SUCCESS, BAD_REQUEST, UNAUTHORIZED, NOT_FOUND, INTERNAL_SERVER_ERROR, PAYLOAD_TOO_LARGE

# 定义泛型类型变量，用于data字段
T = TypeVar('T')

# 统一响应基类
class BaseResponse(BaseModel, Generic[T]):
    """统一API响应格式"""
    code: int = Field(..., description="HTTP状态码", example=200)
    message: str = Field(..., description="响应消息", example="Success")
    data: Optional[T] = Field(None, description="响应数据")

# 工具函数：创建成功响应
def create_success_response(data: T, message: str = STATUS_MESSAGES[SUCCESS]) -> BaseResponse[T]:
    """创建成功响应"""
    return BaseResponse[T](
        code=SUCCESS,
        message=message,
        data=data
    )

# 工具函数：创建错误响应
def create_error_response(code: HttpStatusCode, message: str) -> BaseResponse[None]:
    """创建错误响应"""
    if not message:
        message = STATUS_MESSAGES.get(code, "Unknown Error")
    
    return BaseResponse[None](
        code=code,
        message=message,
        data=None
    )

# 特定错误响应函数
def create_bad_request_response(message: str = "请求参数错误") -> BaseResponse[None]:
    """创建400错误响应"""
    return create_error_response(BAD_REQUEST, message)

def create_unauthorized_response(message: str = "身份认证失败") -> BaseResponse[None]:
    """创建401错误响应"""
    return create_error_response(UNAUTHORIZED, message)

def create_not_found_response(message: str = "资源不存在") -> BaseResponse[None]:
    """创建404错误响应"""
    return create_error_response(NOT_FOUND, message)

def create_payload_too_large_response(message: str = "请求体过大") -> BaseResponse[None]:
    """创建413错误响应（Payload Too Large）"""
    return create_error_response(PAYLOAD_TOO_LARGE, message)

def create_internal_error_response(message: str = "服务器内部错误") -> BaseResponse[None]:
    """创建500错误响应"""
    return create_error_response(INTERNAL_SERVER_ERROR, message)


# 在文件末尾添加以下代码

from typing import Callable, Optional, Any
from functools import wraps

def validator(
    condition: Callable[[Any], bool],
    error_response: Callable[[str], BaseResponse[None]],
    error_message: str
) -> Callable:
    """验证器装饰器工厂"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not condition(*args, **kwargs):
                return error_response(error_message)
            return func(*args, **kwargs)
        return wrapper
    return decorator

# 常用的验证条件函数
def not_empty(value: Any) -> bool:
    """检查值不为空"""
    if hasattr(value, '__len__'):
        return len(value) > 0
    return value is not None

def max_length(value: Any, max_len: int) -> bool:
    """检查长度不超过最大值"""
    if hasattr(value, '__len__'):
        return len(value) <= max_len
    return True

def is_supported_file_type(filename: str, supported_extensions: list) -> bool:
    """检查文件类型是否支持"""
    _, ext = os.path.splitext(filename)
    return ext.lower() in supported_extensions