"""
Data Schemas (Pydantic Models)
==============================

This module defines Pydantic models used for data validation, serialization, and API interactions.
These schemas ensure that data exchanged between the API endpoints and the internal logic
adheres to defined structures.

Key Models:
-----------
-   **TaskBase**: Base model containing common fields for a Task.
-   **TaskCreate**: Schema for task creation requests.
-   **TaskOut**: Schema for task responses, including JSON-serialized output info.
"""
from pydantic import BaseModel, Json
from typing import Optional, Dict, Any
from const.task_status_enum import TaskStatus


# --------- Task ---------
class TaskBase(BaseModel):
    """
    Base Schema for Task
    --------------------
    Contains the fundamental fields shared across creation and response models.

    Fields:
        task_id (str): Unique task identifier.
        bucket_name (str): Source bucket name.
        object_key (str): Source file path.
        output_bucket (str): Destination bucket name.
        formula_enabled (int): Toggle for formula recognition.
        ocr_enabled (int): Toggle for OCR.
        table_enabled (int): Toggle for table recognition.
        ocr_lang (str): OCR language code.
        output_info (str): Raw output information string.
        status (TaskStatus): Current task status.
    """
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