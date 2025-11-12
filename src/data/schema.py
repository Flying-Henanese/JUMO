from pydantic import BaseModel, Json
from typing import Optional, Dict, Any
from const.task_status_enum import TaskStatus


# --------- Task ---------
class TaskBase(BaseModel):
    task_id: str
    bucket_name: Optional[str] = None
    object_key: str
    output_bucket: Optional[str] = None
    formula_enabled: int = 0
    ocr_enabled: int = 0
    table_enabled: int = 0
    ocr_lang: Optional[str] = None
    output_info: Optional[str] = ''
    status: TaskStatus = TaskStatus.QUEUED

class TaskCreate(TaskBase):
    pass

class TaskOut(TaskBase):
    task_id: str
    output_info: Json[Dict[str,Any]] = {}

    class Config:
        from_attributes = True