from fastapi import HTTPException
from minio import Minio
import os
import io
from loguru import logger
from minio.error import S3Error
from threading import Lock

class MinioConnection:
    '''
    单例模式下的Minio连接
    在这里定义统一的minio操作
    包括：
    - 上传文件
    - 下载文件
    - 删除文件
    '''

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        endpoint = os.getenv('MINIO_ENDPOINT')
        access_key = os.getenv('MINIO_ACCESS_KEY')
        secret_key = os.getenv('MINIO_SECRET_KEY')
        secure = os.getenv('MINIO_SECURE', 'false').lower() == 'true'

        if not all([endpoint, access_key, secret_key]):
            raise RuntimeError("MinIO环境变量配置不完整，请检查 MINIO_ENDPOINT、ACCESS_KEY、SECRET_KEY、BUCKET_NAME")

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        logger.info(f"初始化Minio连接: endpoint={endpoint}")

# region
    # # 初始化一个OSS连接
    # def __init__(self):
    #     self.client = Minio(
    #         endpoint=os.getenv('MINIO_ENDPOINT'),
    #         access_key=os.getenv('MINIO_ACCESS_KEY'),
    #         secret_key=os.getenv('MINIO_SECRET_KEY'),
    #         secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
    #     )
    #     logger.info(f"初始化Minio连接，endpoint: {os.getenv('MINIO_ENDPOINT')}, bucket_name: {os.getenv('MINIO_BUCKET_NAME')}")
    #     # 注意这里是默认值,
    #     # self.bucket_name = os.getenv('MINIO_BUCKET_NAME')
# endregion
    def upload_file_by_path(self, object_name: str, bucket_name:str, file_path: str) -> bool:
        try:
            self.client.fput_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            logger.info(f"文件上传成功: bucket:{bucket_name};object_name:{object_name};file_path:{file_path}")
            return True
        except Exception as e:
            logger.error(f"文件上传失败: bucket:{bucket_name};object_name:{object_name};file_path:{file_path}, 异常：{e}")
            return False

    def upload_file_by_bytes(self,
        object_name: str, 
        bucket_name: str, 
        file_bytes: bytes,
        content_type: str) -> bool:
        try:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=io.BytesIO(file_bytes),
                length=len(file_bytes)
            )
            return True
        except Exception as e:
            logger.error(f"文件上传失败: bucket:{bucket_name};object_name:{object_name}, 异常：{e}")
            return False

    def download_file(self, object_name: str, bucket_name:str, file_path: str) -> bool:
        success = False
        try:
            self.client.fget_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            success = True
        except Exception as e:
            logger.error(f"文件下载失败: {e}")
            raise(f"Download failed: {e}")
        finally:    
            return success

    def delete_file(self, object_name: str) -> bool:
        success = False
        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            success = True
            logger.info(f'删除文件成功: {object_name}')
            return success
        except Exception as e:
            logger.error(f'删除文件失败: {object_name}, 异常: {e}')
            raise(f'删除文件失败: {e}')
            return success

    def get_file_byte(self,object_name: str,bucket_name:str) -> bytes:
        try:
            response = self.client.get_object(
                bucket_name=bucket_name,
                object_name=object_name
            )
            return response.read()
        except Exception as e:
            logger.error(f'获取文件失败: {object_name}')
            raise(f'获取文件失败: {e}')

    def file_exists(self,object_name: str,bucket_name:str) -> bool:
        try:
            self.client.stat_object(bucket_name,object_name)
            return True
        except S3Error as e:
            if "NoSuchKey" in str(e):
                return False
            logger.error(f"文件不存在: {e}, object_name: {object_name}, bucket_name: {bucket_name}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {e}")
    
    def bucket_exists(self, bucket_name: str) -> bool:
        """
        检查存储桶是否存在
        :param bucket_name: 存储桶名称
        :return: 存在返回True，否则返回False
        """
        try:
            return self.client.bucket_exists(bucket_name)
        except Exception as e:
            logger.error(f"检查存储桶失败: {bucket_name}, 异常: {e}")
            return False
