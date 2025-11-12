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
    这个类实现的作用就是把ORM模型转换为pydantic模型
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
    # 状态（替代 ActiveTask 表）
    status = Column(String, nullable=False, default=TaskStatus.QUEUED)

    def __repr__(self):
        return f'''Task(id={self.id}, task_id={self.task_id}, bucket_name={self.bucket_name}, object_key={self.object_key}, output_bucket={self.output_bucket}, ocr_enabled={self.ocr_enabled}, table_enabled={self.table_enabled}, ocr_lang={self.ocr_lang}, output_info={self.output_info}, create_time={self.create_time}, finish_time={self.finish_time})'''

class TaskResponse(BaseModel):
    '''响应模型,用于封装任务数据'''
    task_id: str
    status:str
    output_bucket:str
    output_info:Optional[dict]

    @classmethod
    def from_orm(cls,task:Task):
        '''从orm模型转换为响应模型'''
        is_completed = False
        try:
            json.loads(task.output_info)
            is_completed = True
        except:
            pass
        return cls(
            task_id=task.task_id,
            status=task.status,
            output_bucket=task.output_bucket,
            output_info=json.loads(task.output_info) if is_completed else None
            )