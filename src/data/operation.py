from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from model import Task, ActiveTask
from schema import TaskCreate, ActiveTaskCreate
from model import Base

class TaskRepository:
    def __init__(self, db_url: str = "sqlite:////Users/zhoushujian/Projects/MinerU-Service/database/mineru"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=self.engine)

    # --------- Task ---------
    # 对于Task表的操作

    # 统一使用实例方法
    def create_task(self, task: TaskCreate) -> Task:
        '''
        创建任务
        '''
        db = self.SessionLocal()
        try:
            db_task = Task(**task.dict())
            db.add(db_task)
            db.commit()
            db.refresh(db_task)
            return db_task
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
            return db.query(Task).filter(Task.task_id == task_id).first()
        finally:
            db.close()

    def list_tasks(self, skip: int = 0, limit: int = 10) -> List[Task]:
        db = self.SessionLocal()
        try:
            return db.query(Task).offset(skip).limit(limit).all()
        finally:
            db.close()

    # --------- ActiveTask ---------
    # 对于ActiveTask表的操作

    def create_active_task(self, active: ActiveTaskCreate) -> ActiveTask:
        '''
        创建一个正在执行的任务
        :param: ActiveTaskCreate类型对象(任务详情)
        :return: ActiveTask类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            db_active = ActiveTask(**active.model_dump())
            db.add(db_active)
            db.commit()
            db.refresh(db_active)
            return db_active
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

    def activate_task_by_id(self, task_id: str, status: str) -> ActiveTask:
        '''
        激活一个任务令其开始执行
        :param: task_id: 任务ID
        :param: status: 任务状态
        :return: ActiveTask类型对象(任务详情)
        '''
        db = self.SessionLocal()
        try:
            active_task = db.query(ActiveTask).filter(ActiveTask.task_id == task_id).first()
            if active_task:# 如果是已经存在的任务
                # 那么久更新状态
                active_task.status = "running" # 
                db.commit()
                db.refresh(active_task)
                return active_task
            else:# 如果是新任务
                # 那么久添加到active_task列表中
                active_task = ActiveTaskCreate(task_id=task_id, status=status)
                return self.create_active_task(active_task)
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

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
                    .filter(ActiveTask.status == "QUEUED")
                    .order_by(ActiveTask.queued_time)
                    .first()
                )
                
                if next_task:
                    # 更新状态为运行中
                    next_task.status = "RUNNING"
                    db.commit()
                    db.refresh(next_task)
                    
                return next_task
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
                .filter(ActiveTask.status == "QUEUED")
                .order_by(ActiveTask.start_time)
                .first()
            )
        finally:
            db.close()

if __name__ == "__main__":
    task = TaskRepository()
    record = task.get_active_tasks()
    print(task.get_active_tasks())

