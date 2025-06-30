from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from typing import Optional
import json
from pydantic import BaseModel

from const.task_status_enum import TaskStatus

Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, unique=True, nullable=False)
    bucket_name = Column(String)
    object_key = Column(String, nullable=False)
    output_bucket = Column(String)
    formula_enabled = Column(Integer, nullable=False, default=0)
    ocr_enabled = Column(Integer, nullable=False, default=0)
    table_enabled = Column(Integer, nullable=False, default=0)
    ocr_lang = Column(String)
    output_info = Column(Text, default='')
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    finish_time = Column(DateTime)
    active_task = relationship("ActiveTask", uselist=False, back_populates="task")

    def __repr__(self):
        return f'''Task(id={self.id}, task_id={self.task_id}, bucket_name={self.bucket_name}, object_key={self.object_key}, output_bucket={self.output_bucket}, ocr_enabled={self.ocr_enabled}, table_enabled={self.table_enabled}, ocr_lang={self.ocr_lang}, output_info={self.output_info}, create_time={self.create_time}, finish_time={self.finish_time})'''
class TaskResponse(BaseModel):
    '''响应模型,用于封装任务数据'''
    task_id: str
    status:str
    output_info:Optional[dict]

    @classmethod
    def from_orm(cls,task):
        '''从orm模型转换为响应模型'''
        is_completed = False
        try:
            json.loads(task.output_info)
            is_completed = True
        except:
            pass
        return cls(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED if is_completed else TaskStatus.FAILED,
            output_info=json.loads(task.output_info) if is_completed else None
            )

class ActiveTask(Base):
    __tablename__ = "active_tasks"
    task_id = Column(String, ForeignKey("tasks.task_id"), primary_key=True)
    start_time = Column(DateTime, server_default=func.current_timestamp())
    queued_time = Column(DateTime)
    status = Column(String, nullable=False)
    task = relationship("Task", back_populates="active_task")

    def __repr__(self):
        return f"ActiveTask(task_id={self.task_id}, start_time={self.start_time}, queued_time={self.queued_time}, status={self.status})"