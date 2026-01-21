"""
Database Operations
===================

This module encapsulates all database interactions through the `TaskRepository` class.
It handles the creation, retrieval, and updating of Task records using SQLAlchemy sessions.
It also manages the database connection lifecycle.

Key Features:
-------------
-   **Session Management**: Automatically handles session creation, commit, rollback, and closure.
-   **CRUD Operations**: Provides methods to create, read, and update tasks.
-   **Logging**: Integrates with `loguru` and custom decorators to log operation time and errors.
"""
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from data.model import Task
from typing import Optional, TypeVar
from data.model import Base # 引入Base模型类
from const.task_status_enum import TaskStatus
from fastapi import HTTPException
from loguru import logger
import os

from wrapper.logger import log_with_time_consumption

# 添加类型变量定义
T = TypeVar('T')

class TaskRepository:
    """
    Repository for Task Operations
    ------------------------------
    Manages all database interactions related to the `Task` model.
    It acts as an abstraction layer between the business logic and the database.

    Attributes:
        engine (Engine): SQLAlchemy Engine instance.
        SessionLocal (sessionmaker): Factory for creating new database sessions.
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
        Base.metadata.create_all(bind=self.engine)
        # self.clear_active_tasks()  # 清理掉之前的active_task表的内容

    # --------- Task ---------
    # 对于Task表的操作

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
        根据任务ID获取任务详情（返回 ORM Task 对象）
        '''
        db = self.SessionLocal()
        try:
            return db.query(Task).filter(Task.task_id == task_id).first()
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

    @log_with_time_consumption(level = "INFO")
    def activate_task_by_id(self, task_id: str, status: TaskStatus) -> Task:
        '''
        将任务标记为指定状态（通常为 PROCESSING）
        '''
        db = self.SessionLocal()
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            task.status = status
            db.commit()
            db.refresh(task)
            return task
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    @log_with_time_consumption(level = "INFO")
    def complete_task(self, task_id: str, succeeded: bool = True) -> Optional[Task]:
        '''
        完成当前任务，并返回队列中最早的待处理任务
        '''
        from datetime import datetime
        db = self.SessionLocal()
        try:
            # 完成当前任务
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task:
                task.finish_time = datetime.now()
                task.status = TaskStatus.COMPLETED if succeeded else TaskStatus.FAILED
                db.commit()
                db.refresh(task)

            # 选择下一个 QUEUED 任务（按创建时间最早）
            next_task = (
                db.query(Task)
                .filter(Task.status == TaskStatus.QUEUED)
                .order_by(Task.create_time)
                .first()
            )
            return next_task
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_queued_task(self) -> Optional[Task]:
        '''
        获取队列中的最早任务（状态为 QUEUED）
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(Task)
                .filter(Task.status == TaskStatus.QUEUED)
                .order_by(Task.create_time)
                .first()
            )
        finally:
            db.close()

    def is_any_active_task(self) -> bool:
        '''
        判断是否有正在执行的任务（PROCESSING）
        '''
        db = self.SessionLocal()
        try:
            return db.query(Task).filter(Task.status == TaskStatus.PROCESSING).first() is not None
        finally:
            db.close()

    def count_active_task(self) -> int:
        '''
        统计排队中的任务数量（QUEUED）
        '''
        db = self.SessionLocal()
        try:
            return db.query(Task).filter(Task.status == TaskStatus.QUEUED).count()
        finally:
            db.close()

    def count_processing_task(self) -> int:
        '''
        统计正在执行的任务数量（PROCESSING）
        '''
        db = self.SessionLocal()
        try:
            return db.query(Task).filter(Task.status == TaskStatus.PROCESSING).count()
        finally:
            db.close()

    # 活跃任务：查询状态为QUEUED 与 PROCESSING 状态的任务
    def get_active_task(self, task_id: str) -> Optional[Task]:
        '''
        根据任务ID获取活跃任务（使用 Task.status 判断，包含 QUEUED 与 PROCESSING）
        :param: task_id: 任务ID
        :return: Task类型对象(活跃任务) 或 None
        '''
        db = self.SessionLocal()
        try:
            return (
                db.query(Task)
                .filter(Task.task_id == task_id)
                .filter(Task.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]))
                .first()
            )
        finally:
            db.close()