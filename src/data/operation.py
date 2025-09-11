from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, delete
from data.model import Task, ActiveTask, TaskResponse
from typing import List, Optional, TypeVar
from data.schema import ActiveTaskCreate
from data.model import Base
from const.task_status_enum import TaskStatus
from fastapi import HTTPException
from loguru import logger
import os
from contextlib import contextmanager
from typing import Callable

from wrapper.logger import log_with_time_consumption

# 添加类型变量定义
T = TypeVar('T')

class TaskRepository:
    """
    定义对Task表(任务信息表)的所有操作
    """
    def __init__(self, db_url: str = None):
        """
        初始化TaskRepository
        :param db_url: 数据库连接字符串,默认使用环境变量MINERU_DB_URL,如果未设置,则使用默认路径
        """
        if db_url is None and not os.getenv("MINERU_DB_URL"):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'database', 'mineru')
            db_url = f"sqlite:///{db_path}"
            logger.info(f"使用默认路径初始化数据库: {db_url}")
        elif os.getenv("MINERU_DB_URL"):
            db_url = f'sqlite:///{os.getenv("MINERU_DB_URL")}'
            logger.info(f"使用环境变量MINERU_DB_URL初始化数据库: {db_url}")
        # 创建sqlite连接引擎
        # 连接参数check_same_thread=False用于支持多线程环境
        # 因为sqlite的写入行为是串行的，所以不会产生线程安全问题
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        # 用来创建数据库会话
        # 1. bind=self.engine 绑定到创建的引擎
        # 2. autoflush=False 禁用自动刷新，需要使用flush()手动刷新才会同步到数据库
        # 3. autocommit=False 自动提交事务，需要手动commit才会将变更保存到数据库，方便回滚
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        # 扫描所有继承自base的ORM模型类，自动创建对应的数据库表（如果在新环境没有sqlite文件也会创建）
        # 注意：如果数据库表已经存在，会忽略重复创建的操作
        Base.metadata.create_all(bind=self.engine)
        self.clear_active_tasks()  # 新增：初始化时清理active_task表

    def clear_active_tasks(self):
        """清理active_task表中的所有记录"""
        db = self.SessionLocal()
        try:
            db.execute(delete(ActiveTask))
            db.commit()
            logger.info("成功清除active_task表")
        except Exception as e:
            db.rollback()
            logger.error(f"清除active_task表失败: {e}")
        finally:
            db.close()

    # --------- Task ---------
    # 对于Task表的操作

    # 统一使用实例方法
    @log_with_time_consumption(level = "INFO")
    def create_task(self, task: Task) -> Task:
        '''
        创建任务
        '''
        db = self.SessionLocal()
        try:
            db.add(task)
            db.commit()
            db.refresh(task)
            return task
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


    def get_task_by_id(self, task_id: str) -> Task:
        '''
        根据任务ID获取任务详情
        :param task_id: 任务ID
        :return: Task类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            return TaskResponse.from_orm(task) if task else None
        finally:
            db.close()

    def list_tasks(self, skip: int = 0, limit: int = 10) -> List[Task]:
        db = self.SessionLocal()
        try:
            return db.query(Task).offset(skip).limit(limit).all()
        finally:
            db.close()

    @log_with_time_consumption(level = "INFO")
    def update_task(self, task: Task) -> Task:
        '''
        通过传入的task对象更新task表中的记录
        :param: Task类型对象(任务详情)
        :return: Task类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            db_task = db.query(Task).filter(Task.task_id == task.task_id).first()
            if db_task:
                db_task.finish_time = task.finish_time
                db_task.output_info = task.output_info
                db.commit()
                db.refresh(db_task)
                return db_task
            else:
                raise HTTPException(status_code=404, detail="Task not found")
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


    # --------- ActiveTask ---------
    # 对于ActiveTask表的操作
    @log_with_time_consumption(level = "INFO")
    def create_active_task(self, active: ActiveTask) -> ActiveTask:
        '''
        创建一个正在执行的任务
        :param: ActiveTaskCreate类型对象(任务详情)
        :return: ActiveTask类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            db.add(active)
            db.commit()
            db.refresh(active)
            return active
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_active_task(self, task_id: str) -> ActiveTask:
        '''
        根据任务ID获取任务详情
        :param: task_id: 任务ID
        :return: ActiveTask类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            return db.query(ActiveTask).filter(ActiveTask.task_id == task_id).first()
        finally:
            db.close()
    @log_with_time_consumption(level = "INFO")
    def activate_task_by_id(self, task_id: str, status: TaskStatus) -> ActiveTask:
        '''
        激活一个已经存在的任务标记其开始执行
        :param: task_id: 任务ID
        :param: status: 任务状态
        :return: ActiveTask类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            active_task = db.query(ActiveTask).filter(ActiveTask.task_id == task_id).first()
            if active_task:# 如果是已经存在的任务
                # 那么久更新状态
                active_task.status = TaskStatus.PROCESSING # 
                db.commit()
                db.refresh(active_task)
                return active_task
            else:# 如果是新任务
                # 那么久添加到active_task列表中
                # 不管之前有没有正在运行的任务
                # 这里都标记为正在排队，这样的话下次就可以从队列中取出任务了
                active_task = ActiveTaskCreate(task_id=task_id, status=TaskStatus.QUEUED)
                return self.create_active_task(active_task)
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    @log_with_time_consumption(level = "INFO")
    def complete_task(self, task_id: str) -> Optional[ActiveTask]:
        '''
        完成分析任务并获取下一个待处理任务
        1. 从active_task列表中删除当前任务
        2. 获取最早进入队列的待处理任务
        :param: task_id: 要完成的任务ID
        :return: 下一个待处理的ActiveTask对象，如果没有则返回None
        '''
        db = self.SessionLocal()
        try:
            active_task = db.query(ActiveTask).filter(ActiveTask.task_id == task_id).first()
            if active_task:
                db.delete(active_task)
                db.commit()
                
                # 2. 获取下一个QUEUED状态的任务
                next_task = (
                    db.query(ActiveTask)
                    .filter(ActiveTask.status == TaskStatus.QUEUED)
                    .order_by(ActiveTask.queued_time)
                    .first()
                )
                
                if next_task:
                    # 更新状态为运行中
                    next_task.status = TaskStatus.PROCESSING
                    db.commit()
                    db.refresh(next_task)
                    return db.query(Task).filter(Task.task_id == next_task.task_id).first()
            return None
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_queued_task(self) -> ActiveTask:
        '''
        获取队列中的最早的任务
        然后开始执行这个任务
        讲究一个先来后到
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(ActiveTask)
                .filter(ActiveTask.status == TaskStatus.QUEUED)
                .order_by(ActiveTask.start_time)
                .first()
            )
        finally:
            db.close()
    
    def is_any_active_task(self) -> ActiveTask:
        '''
        判断是否有正在执行的任务
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(ActiveTask)
                .filter(ActiveTask.status == "PROCESSING")
                .first()
            )
        finally:
            db.close()


    def count_active_task(self) -> int:
        '''
        统计正在执行的任务数量
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(ActiveTask)
                .filter(ActiveTask.status == TaskStatus.QUEUED)
                .count()
            )
        finally:
            db.close()

    def count_processing_task(self) -> int:
        '''
        统计正在执行的任务数量
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(ActiveTask)
                .filter(ActiveTask.status == TaskStatus.PROCESSING)
                .count()
            )
        finally:
            db.close()
    
