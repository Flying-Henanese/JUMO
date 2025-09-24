"""
HTTP状态码常量定义

提供标准的HTTP状态码常量，用于统一API响应
"""

from enum import IntEnum

class HttpStatusCode(IntEnum):
    """HTTP状态码枚举"""
    
    # 2xx Success
    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    
    # 4xx Client Errors
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    PAYLOAD_TOO_LARGE = 413
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    
    # 5xx Server Errors
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504

# 状态码描述映射
STATUS_MESSAGES = {
    # 2xx
    HttpStatusCode.SUCCESS: "Success",
    HttpStatusCode.CREATED: "Created",
    HttpStatusCode.ACCEPTED: "Accepted",
    HttpStatusCode.NO_CONTENT: "No Content",
    
    # 4xx
    HttpStatusCode.BAD_REQUEST: "Bad Request",
    HttpStatusCode.UNAUTHORIZED: "Unauthorized",
    HttpStatusCode.FORBIDDEN: "Forbidden",
    HttpStatusCode.NOT_FOUND: "Not Found",
    HttpStatusCode.METHOD_NOT_ALLOWED: "Method Not Allowed",
    HttpStatusCode.CONFLICT: "Conflict",
    HttpStatusCode.PAYLOAD_TOO_LARGE: "Payload Too Large",
    HttpStatusCode.UNPROCESSABLE_ENTITY: "Unprocessable Entity",
    HttpStatusCode.TOO_MANY_REQUESTS: "Too Many Requests",
    
    # 5xx
    HttpStatusCode.INTERNAL_SERVER_ERROR: "Internal Server Error",
    HttpStatusCode.NOT_IMPLEMENTED: "Not Implemented",
    HttpStatusCode.BAD_GATEWAY: "Bad Gateway",
    HttpStatusCode.SERVICE_UNAVAILABLE: "Service Unavailable",
    HttpStatusCode.GATEWAY_TIMEOUT: "Gateway Timeout",
}

# 常用状态码别名
SUCCESS = HttpStatusCode.SUCCESS
BAD_REQUEST = HttpStatusCode.BAD_REQUEST
UNAUTHORIZED = HttpStatusCode.UNAUTHORIZED
NOT_FOUND = HttpStatusCode.NOT_FOUND
INTERNAL_SERVER_ERROR = HttpStatusCode.INTERNAL_SERVER_ERROR
PAYLOAD_TOO_LARGE = HttpStatusCode.PAYLOAD_TOO_LARGE