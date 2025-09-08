from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from typing import Optional
import json
from pydantic import BaseModel

from const.task_status_enum import TaskStatus

# 提供整个项目的ORM模型
# 所有定义对模型操作的类都要继承Base 数据库模型的唯一入口点
# 这个基类是连接Python世界中的对象和关系型数据库中表的桥梁
Base = declarative_base()

class Task(Base):
    """
    任务列表
    记录所有的分析任务
    """
    # 表名
    __tablename__ = "tasks" 
    # 主键id
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 任务id,通过简化版uuid生成
    task_id = Column(String, unique=True, nullable=False)
    # 源文件所在的桶名 
    bucket_name = Column(String)
    # 源文件的文件名
    object_key = Column(String, nullable=False)
    # 输出文件所在的桶名
    output_bucket = Column(String)
    # 公式识别是否开启
    formula_enabled = Column(Integer, nullable=False, default=0)
    # ocr识别是否开启
    ocr_enabled = Column(Integer, nullable=False, default=0)
    # 表格识别是否开启
    table_enabled = Column(Integer, nullable=False, default=0)
    # ocr识别语言
    ocr_lang = Column(String)
    # 输出信息,json格式
    output_info = Column(Text, default='')
    # 创建时间
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    # 完成时间
    finish_time = Column(DateTime)
    # 外键约束,关联ActiveTask表
    active_task = relationship("ActiveTask", uselist=False, back_populates="task")

    def __repr__(self):
        return f'''Task(id={self.id}, task_id={self.task_id}, bucket_name={self.bucket_name}, object_key={self.object_key}, output_bucket={self.output_bucket}, ocr_enabled={self.ocr_enabled}, table_enabled={self.table_enabled}, ocr_lang={self.ocr_lang}, output_info={self.output_info}, create_time={self.create_time}, finish_time={self.finish_time})'''
class TaskResponse(BaseModel):
    '''响应模型,用于封装任务数据'''
    task_id: str
    status:str
    output_bucket:str
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
            output_bucket=task.output_bucket,
            output_info=json.loads(task.output_info) if is_completed else None
            )

class ActiveTask(Base):
    """
    活跃任务模型
    
    用于记录当前正在执行或排队的任务状态信息。
    通过task_id与Task表建立一对一关系，用于跟踪任务的实时状态。
    
    Attributes
    ----------
    task_id : str
        任务ID，作为外键关联到tasks表的task_id字段，同时也是主键
    start_time : datetime
        任务开始执行的时间戳，由数据库自动生成
    queued_time : datetime, optional
        任务进入排队队列的时间戳，可为空
    status : str
        任务当前状态（如：pending, running, completed, failed等）
    task : Task
        关联的Task对象，通过SQLAlchemy relationship建立反向引用
    
    Notes
    -----
    该表与Task表形成一对一关系，通过task_id字段进行关联。
    当任务完成或失败后，对应的ActiveTask记录通常会被删除。
    """
    __tablename__ = "active_tasks"
    task_id = Column(String, ForeignKey("tasks.task_id"), primary_key=True)
    start_time = Column(DateTime, server_default=func.current_timestamp())
    queued_time = Column(DateTime)
    status = Column(String, nullable=False)
    task = relationship("Task", back_populates="active_task")

    def __repr__(self):
        return f"ActiveTask(task_id={self.task_id}, start_time={self.start_time}, queued_time={self.queued_time}, status={self.status})"