from sre_parse import SUCCESS
from fastapi import HTTPException
from minio import Minio
import os
import io
from typing import Optional, BinaryIO
import minio

from minio.error import S3Error

class MinioConnection:
    # 初始化一个OSS连接
    def __init__(self):
        self.client = Minio(
            endpoint=os.getenv('MINIO_ENDPOINT'),
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        )
        # 注意这里是默认值,
        # self.bucket_name = os.getenv('MINIO_BUCKET_NAME')

    def upload_file_by_path(self, object_name: str, bucket_name:str, file_path: str) -> bool:
        try:
            self.client.fput_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            return True
        except Exception as e:
            print(f"Upload failed: {e}")
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
            print(f"Upload from bytes failed: {e}")
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
            raise(f"Download failed: {e}")
        finally:    
            return success

    def delete_file(self, object_name: str) -> bool:
        sucess = False
        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            success = True
        except Exception as e:
            raise(f'删除文件失败: {e}')
        finally:
            return success

    def get_file_byte(self,object_name: str,bucket_name:str) -> bytes:
        try:
            response = self.client.get_object(
                bucket_name=bucket_name,
                object_name=object_name
            )
            return response.read()
        except Exception as e:
            raise(f'获取文件失败: {e}')

    def file_exists(self,object_name: str,bucket_name:str) -> bool:
        try:
            self.client.stat_object(bucket_name,object_name)
            success = True
        except S3Error as e:
            raise HTTPException(status_code=404, detail=f"文件不存在: {e}")
        finally:
            return success