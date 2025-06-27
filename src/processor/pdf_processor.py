from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.data.read_api import read_local_images, read_local_office
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.data.data_reader_writer import FileBasedDataWriter
import os
import tempfile
from data.model import Task
from wrapper.logger import log_with_time_consumption
from utils.minio_tool import MinioConnection
from const.file_extensions import PDF_EXTENSIONS,OFFICE_EXTENSIONS,IMAGE_EXTENSIONS
import json
from fastapi import HTTPException
from data.operation import TaskRepository
from minio.error import S3Error
import datetime


class PDFProcessor:
    def __init__(self,minio_tool:MinioConnection,task_repository:TaskRepository):
        self.minio_tool = minio_tool    
        self.task_repository = task_repository

    @log_with_time_consumption(level = "INFO")
    def _sync_process_pdf(self,current_task:Task):
        try:
            extention = os.path.splitext(current_task.object_key)[-1]
            file_bytes = self.minio_tool.get_file_byte(bucket_name = current_task.bucket_name,object_name = current_task.object_key)
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = os.path.join(temp_dir, "output")
                os.makedirs(output_dir, exist_ok=True)
                # 把文件保存在临时文件夹中
                with open(os.path.join(temp_dir, os.path.basename(current_task.object_key)), "wb") as f:
                    f.write(file_bytes)
                    # 读取pdf文件为pymudoc对象
                    if extention in PDF_EXTENSIONS:
                        # 读取pdf文件为pymupdf数据集
                        ds = PymuDocDataset(file_bytes)
                    elif extention in OFFICE_EXTENSIONS:
                        # 需要使用office解析器把文档解析为pymudoc数据列表
                        ds = read_local_office(temp_dir)[0]
                    elif extention in IMAGE_EXTENSIONS:
                        # 读取图片文件为一个数据集
                        ds = read_local_images(temp_dir)[0]
                    else:
                        raise HTTPException(status_code=400, detail="不支持的文件类型")
            # 获取pdf文件的名称，不包含后缀
            name_without_ext = os.path.splitext(os.path.basename(current_task.object_key))[0]
            # 存储文档中所有的图片
            images_list = []
            # 使用临时文件进行相关的操作
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = os.path.join(temp_dir, "output")
                os.makedirs(output_dir, exist_ok=True)

                # 判断PDF文档类型是否需要使用OCR进行处理
                if ds.classify() == SupportedPdfParseMethod.OCR:
                    # 如果是OCR类型，使用OCR模式进行分析
                    infer_result = ds.apply(
                        doc_analyze, 
                        ocr=current_task.ocr_enabled, # 如果支持OCR,就按照用户传参指定是否使用
                        table_enable = current_task.table_enabled,
                        lang = current_task.ocr_lang )
                    # 为OCR模式也指定输出目录
                    pipe_result = infer_result.pipe_ocr_mode(FileBasedDataWriter(output_dir))
                else:
                    # 如果不是OCR类型，使用普通文本模式进行分析
                    infer_result = ds.apply(doc_analyze, ocr=False)
                    # 使用文本模式处理分析结果，并指定输出目录
                    pipe_result = infer_result.pipe_txt_mode(FileBasedDataWriter(output_dir))
                
                # 提取并上传图片
                # 同时将图片
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                            with open(os.path.join(root, file), 'rb') as img_file:
                                # 把图片先放入oss
                                self.minio_tool.upload_file_by_bytes(
                                    bucket_name = current_task.output_bucket,
                                    object_name=f"{current_task.task_id}/images/{file}",
                                    file_bytes=img_file.read(),
                                    content_type=f"image/{file.split('.')[-1]}"
                                )
                                # 然后再把图片名称放入图片列表
                                images_list.append(f"{current_task.task_id}/images/{file}")
                
                # 生成核心的3个文件
                # 1. markdown文件
                markdown_content = pipe_result.get_markdown(
                    img_dir_or_bucket_prefix=f"{current_task.task_id}/images/"
                )
                # 2. content_list文件
                content_list = json.dumps(pipe_result.get_content_list(image_dir_or_bucket_prefix=f"{current_task.task_id}/images/"))
                # 3. middle_json文件
                middle_json = pipe_result.get_middle_json()


                # 把生成的3个文件全部放入OSS
                self.minio_tool.upload_file_by_bytes(
                    bucket_name = current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}.md",
                    file_bytes=markdown_content.encode('utf-8'),
                    content_type="text/markdown"
                )

                self.minio_tool.upload_file_by_bytes(
                    bucket_name = current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}_content_list.json",
                    file_bytes=content_list.encode('utf-8'),
                    content_type="application/json"
                )

                self.minio_tool.upload_file_by_bytes(
                    bucket_name = current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}_middle.json",
                    file_bytes=middle_json.encode('utf-8'),
                    content_type="application/json"
                )

            current_task.output_info = json.dumps({
                "markdown": f"{current_task.task_id}/{name_without_ext}.md",
                "content_list": f"{current_task.task_id}/{name_without_ext}_content_list.json",
                "middle_json": f"{current_task.task_id}/{name_without_ext}_middle.json",
                "images": images_list
            })
        except S3Error as e:
            current_task.output_info = str(e)
        except Exception as e:
            current_task.output_info = str(e)
        finally:
            # 设置完成时间
            current_task.finish_time = datetime.datetime.now()
            # 把完成的信息写入task表
            self.task_repository.update_task(current_task)
