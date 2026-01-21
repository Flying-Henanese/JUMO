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
        
        # 检查并创建默认的bucket
        # 确保用于上传文件的bucket存在，如果不存在则创建
        self._ensure_default_buckets()

    def _ensure_default_buckets(self):
        """防御性编程，确保默认的用于上传分析文件和存储桶存在，如果不存在则创建"""
        default_buckets = [
            os.getenv('UPLOAD_BUCKET', 'uploads'),    # 上传文件bucket
            os.getenv('MINIO_OUTPUT_BUCKET', 'output') # 输出文件bucket
        ]
        
        for bucket_name in default_buckets:
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name=bucket_name)
                    logger.info(f"创建默认存储桶: {bucket_name}")
                else:
                    logger.debug(f"存储桶已存在: {bucket_name}")
            except Exception as e:
                logger.error(f"检查/创建默认存储桶失败: {bucket_name}, 错误: {e}")
                # 继续尝试其他bucket，不中断初始化
                continue

    def upload_file_by_path(self, object_name: str, bucket_name:str, file_path: str) -> bool:
        """
        通过文件路径上传文件到OSS成为一个文件
        """
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
            """
            上传文件字节流到OSS成为一个文件
            """
            # 确保 file_bytes 是 bytes 类型
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode('utf-8')
            elif not isinstance(file_bytes, bytes):
                raise ValueError(f"file_bytes 必须是 bytes 或 str 类型，当前类型: {type(file_bytes)}")
            
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=io.BytesIO(file_bytes),
                length=len(file_bytes),
                content_type=content_type
            )
            logger.info(f"文件上传成功: bucket:{bucket_name};object_name:{object_name}")
            return True
        except Exception as e:
            logger.error(f"文件上传失败: bucket:{bucket_name};object_name:{object_name}, 异常：{e}")
            return False

    def download_file(self, object_name: str, bucket_name:str, file_path: str) -> bool:
        """
        下载文件到file_path（调用者指定一个文件路径）
        """
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
        """
        删除文件
        """
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
        """
        获取文件的字节流
        """
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
        """
        检查文件是否存在
        """
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

    def list_objects(self, bucket_name: str, prefix: str = "", recursive: bool = True) -> list:
        """
        列出存储桶中的对象，支持前缀过滤
        :param bucket_name: 存储桶名称
        :param prefix: 对象前缀过滤
        :param recursive: 是否递归搜索
        :return: 对象名称列表
        """
        try:
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
            return [obj.object_name for obj in objects]
        except Exception as e:
            logger.error(f"列出对象失败: bucket={bucket_name}, prefix={prefix}, 异常: {e}")
            return []

    def find_files_by_pattern(self, bucket_name: str, pattern: str) -> list:
        """
        根据通配符模式查找文件
        :param bucket_name: 存储桶名称
        :param pattern: 通配符模式（如："*middle.json"）
        :return: 匹配的文件路径列表
        """
        import fnmatch
        
        # 提取前缀用于优化搜索
        if "*" in pattern:
            prefix = pattern.split("*")[0]
        else:
            prefix = ""
        
        all_objects = self.list_objects(bucket_name, prefix=prefix)
        matching_files = fnmatch.filter(all_objects, pattern)
        
        return matching_files
