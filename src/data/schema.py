from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# --------- Task ---------
class TaskBase(BaseModel):
    task_id: str
    bucket_name: Optional[str] = None
    object_key: str
    output_bucket: Optional[str] = None
    ocr_enabled: int = 0
    table_enabled: int = 0
    ocr_lang: Optional[str] = None
    output_info: Optional[str] = ''

class TaskCreate(TaskBase):
    pass

class TaskOut(TaskBase):
    id: int
    create_time: datetime
    finish_time: Optional[datetime] = None

    class Config:
        from_attributes = True

# --------- ActiveTask ---------
class ActiveTaskBase(BaseModel):
    task_id: str
    start_time: Optional[datetime] = None
    queued_time: Optional[datetime] = None
    status: str

class ActiveTaskCreate(ActiveTaskBase):
    pass

class ActiveTaskOut(ActiveTaskBase):
    class Config:
        from_attributes = True
