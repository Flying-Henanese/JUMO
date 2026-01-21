from enum import Enum

class TaskStatus(str, Enum):
    '''
    任务状态枚举类
    '''
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


