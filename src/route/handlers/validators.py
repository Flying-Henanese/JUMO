"""
通用API请求验证器模块
提供可重用的验证工具和装饰器
"""

from typing import Callable, Any, Optional, List, Union
from functools import wraps
from .response_handler import BaseResponse, create_bad_request_response, create_payload_too_large_response

class ValidationError(Exception):
    """验证错误异常"""
    def __init__(self, response: BaseResponse[None]):
        self.response = response
        super().__init__(str(response))

# ==================== 通用验证装饰器 ====================

def validate_request(*validators: Callable) -> Callable:
    """
    通用请求验证装饰器
    用法: @validate_request(validator1, validator2, ...)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # 提取请求对象（FastAPI中通常是第二个参数）
                request = None
                # 尝试从args或kwargs中提取请求对象
                if len(args) > 1:
                    request = args[1]
                elif 'request' in kwargs:
                    request = kwargs['request']
                
                # 执行所有验证器
                for validator in validators:
                    if request is not None:
                        validator(request)
                
                return func(*args, **kwargs)
                
            except ValidationError as e:
                return e.response
                
        return wrapper
    return decorator

# ==================== 通用验证条件函数 ====================

def validate_not_none(value: Any, field_name: str = "字段") -> None:
    """验证值不为None"""
    if value is None:
        raise ValidationError(create_bad_request_response(f"{field_name}不能为空"))

def validate_not_empty(value: Any, field_name: str = "字段") -> None:
    """验证值不为空（支持字符串、列表、字典等）"""
    if value is None:
        raise ValidationError(create_bad_request_response(f"{field_name}不能为空"))
    
    if hasattr(value, '__len__') and len(value) == 0:
        raise ValidationError(create_bad_request_response(f"{field_name}不能为空"))

def validate_max_length(value: Any, max_len: int, field_name: str = "字段") -> None:
    """验证长度不超过最大值"""
    if value is not None and hasattr(value, '__len__') and len(value) > max_len:
        raise ValidationError(create_payload_too_large_response(
            f"{field_name}长度不能超过{max_len}"
        ))

def validate_min_length(value: Any, min_len: int, field_name: str = "字段") -> None:
    """验证长度不小于最小值"""
    if value is not None and hasattr(value, '__len__') and len(value) < min_len:
        raise ValidationError(create_bad_request_response(
            f"{field_name}长度不能少于{min_len}"
        ))

def validate_in_range(value: Union[int, float], min_val: Any, max_val: Any, field_name: str = "字段") -> None:
    """验证数值在指定范围内"""
    if value is not None and (value < min_val or value > max_val):
        raise ValidationError(create_bad_request_response(
            f"{field_name}必须在{min_val}到{max_val}之间"
        ))

def validate_regex_pattern(value: str, pattern: str, field_name: str = "字段") -> None:
    """验证字符串匹配正则表达式"""
    import re
    if value is not None and not re.match(pattern, value):
        raise ValidationError(create_bad_request_response(
            f"{field_name}格式不正确"
        ))

# ==================== 特定字段验证器生成器 ====================

def field_validator(field_name: str, validator_func: Callable) -> Callable:
    """为特定字段创建验证器"""
    def validator(request: Any) -> None:
        if hasattr(request, field_name):
            value = getattr(request, field_name)
            validator_func(value, field_name)
    return validator

def list_field_validator(field_name: str, validator_func: Callable) -> Callable:
    """为列表字段的每个元素创建验证器"""
    def validator(request: Any) -> None:
        if hasattr(request, field_name):
            values = getattr(request, field_name)
            if isinstance(values, list):
                for i, value in enumerate(values):
                    try:
                        validator_func(value, f"{field_name}[{i}]")
                    except ValidationError as e:
                        raise ValidationError(create_bad_request_response(
                            f"{field_name}第{i+1}个元素: {e.response.message}"
                        ))
    return validator

# ==================== 常用验证器组合 ====================

def validate_required_fields(*field_names: str) -> Callable:
    """验证必需字段不为空"""
    def validator(request: Any) -> None:
        for field_name in field_names:
            if not hasattr(request, field_name) or getattr(request, field_name) is None:
                raise ValidationError(create_bad_request_response(f"{field_name}为必填字段"))
    return validator

# ==================== 快捷验证器 ====================

# 常用快捷验证器
validate_not_empty_list = lambda field_name: list_field_validator(field_name, validate_not_empty)
validate_max_list_length = lambda field_name, max_len: list_field_validator(
    field_name, lambda value, fn: validate_max_length(value, max_len, fn)
)
