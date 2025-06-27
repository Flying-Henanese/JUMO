from fastapi import HTTPException
from minio import Minio
import os
import io
from loguru import logger
from minio.error import S3Error

class MinioConnection:
    '''
    以后要改成单例模式（同一个配置下的）
    '''

    # 初始化一个OSS连接
    def __init__(self):
        self.client = Minio(
            endpoint=os.getenv('MINIO_ENDPOINT'),
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        )
        logger.info(f"初始化Minio连接，endpoint: {os.getenv('MINIO_ENDPOINT')}, bucket_name: {os.getenv('MINIO_BUCKET_NAME')}")
        # 注意这里是默认值,
        # self.bucket_name = os.getenv('MINIO_BUCKET_NAME')

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
