"""
VLM-based PDF Processor
=======================

This module defines the `PDFProcessor` class, which orchestrates the processing of PDF documents
(and other formats converted to PDF) using a Vision-Language Model (VLM) backend.

Workflow:
---------
1.  **Input Handling**:
    -   Downloads the source file from MinIO.
    -   Converts non-PDF formats (Images, Word, Excel) to PDF.
    -   Validates file extensions against allowed types.

2.  **VLM Analysis (`doc_analyze`)**:
    -   Sends the PDF content to the MinerU VLM backend (via HTTP) for layout analysis and OCR.
    -   Configures processing parameters (formula/table recognition, OCR language) based on task settings.
    -   Generates intermediate JSON (`middle_json`) containing detailed document structure.

3.  **Content Generation**:
    -   Extracts images and uploads them to MinIO.
    -   Generates Markdown content (`vlm_union_make`).
    -   Performs post-processing on Markdown (semantic splitting, header enhancement).

4.  **Result Storage**:
    -   Uploads all artifacts (Markdown, JSON, Images) to the output MinIO bucket.
    -   Updates the task status and output info in the database.

Dependencies:
-------------
-   `mineru` backend for core PDF analysis.
-   `minio_tool` for file storage operations.
-   `TaskRepository` for database updates.
"""
import os
import tempfile
import json
import datetime
import io

from fastapi import HTTPException
from loguru import logger
from minio.error import S3Error

from mineru.cli.common import convert_pdf_bytes_to_bytes_by_pypdfium2, prepare_env
from mineru.data.data_reader_writer import FileBasedDataWriter
from mineru.utils.enum_class import MakeMode
from mineru.backend.vlm.vlm_analyze import doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make
import ray
from ray import serve
import re
from processor.image_processing.image_rag import ImageRAGMetadata


from data.model import Task
from wrapper.logger import log_with_time_consumption
from utils.minio_tool import MinioConnection
from const.file_extensions import OFFICE_EXTENSIONS, PDF_EXTENSIONS,IMAGE_EXTENSIONS,EXCEL_EXTENTIONS
from data.operation import TaskRepository
from processor.markdown_splitter import process_markdown
from processor.converters.file_converters import office_bytes_to_pdf_bytes
from PIL import Image

class PDFProcessor:
    def __init__(self, minio_tool: MinioConnection, task_repository: TaskRepository):
        self.minio_tool: MinioConnection = minio_tool
        self.task_repository: TaskRepository = task_repository
        self._image_rag_handle = None

    def _get_image_rag_handle(self):
        """
        Lazy load and cache the Ray Serve handle.
        This prevents creating a new LongPollClient for every request, reducing log noise.
        """
        if self._image_rag_handle is not None:
            return self._image_rag_handle

        try:
            # app_name matches name in nlp_serve_config.yaml
            target_app_name = os.getenv("IMAGE_RAG_APP_NAME", "image_rag_app")
            self._image_rag_handle = serve.get_deployment_handle("ImageRAGDeployment", app_name=target_app_name)
            logger.info(f"Successfully connected to ImageRAGDeployment (app={target_app_name})")
        except Exception as e:
            logger.warning(f"Failed to get image_rag_handle: {e}")
            self._image_rag_handle = None
        
        return self._image_rag_handle
    
    @log_with_time_consumption(level="INFO")
    # @with_gpu_selection
    def _sync_process_pdf(self, current_task: Task):
        try:
            extension = os.path.splitext(current_task.object_key)[-1].lower()
            if extension not in {*PDF_EXTENSIONS, *IMAGE_EXTENSIONS, *OFFICE_EXTENSIONS,*EXCEL_EXTENTIONS}:
                raise HTTPException(status_code=400, detail="不支持的文件类型")

            file_bytes = self.minio_tool.get_file_byte(
                bucket_name=current_task.bucket_name,
                object_name=current_task.object_key
            )
            # 为了支持图片文件，需要先转换为 PDF
            if extension in IMAGE_EXTENSIONS:
                image_bytes = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                pdf_bytes = io.BytesIO()
                image_bytes.save(pdf_bytes, format="PDF")
                pdf_bytes.seek(0)  # 重置指针到开头
                file_bytes = pdf_bytes.getvalue()  # 获取PDF字节数据
            elif extension in OFFICE_EXTENSIONS or extension in EXCEL_EXTENTIONS:
                file_bytes = office_bytes_to_pdf_bytes(word_bytes=file_bytes,suffix=extension)
            else:
                # do nothing for original pdf files
                pass
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = os.path.join(temp_dir, "output")
                os.makedirs(output_dir, exist_ok=True)

                # 文件名处理
                name_without_ext = os.path.splitext(os.path.basename(current_task.object_key))[0]
                file_name = name_without_ext
                images_list = []

                # 截取页范围（可配置）
                pdf_bytes = convert_pdf_bytes_to_bytes_by_pypdfium2(file_bytes, 0, None)
                # 装饰器：自动选择可用 GPU，并设置 CUDA_VISIBLE_DEVICES
                # pipeline_doc_analyze = with_gpu_selection(pipeline_doc_analyze)

                # 存储文档中所有的图片RAG元数据，使用字典方便通过文件名检索
                image_rag_metadata_map: dict[str, ImageRAGMetadata] = {}
                
                # Get cached handle instead of creating new one every time
                # image_rag_handle = self._get_image_rag_handle()

                local_image_dir, local_md_dir = prepare_env(output_dir, file_name, "auto")
                image_writer, md_writer = FileBasedDataWriter(local_image_dir), FileBasedDataWriter(local_md_dir)

                os.environ['MINERU_VLM_FORMULA_ENABLE'] = 'true' if bool(current_task.formula_enabled) else 'false'
                os.environ['MINERU_VLM_TABLE_ENABLE'] = 'true' if bool(current_task.table_enabled) else 'false'
                os.environ['MINERU_FORMULA_ENABLE'] = 'true' if bool(current_task.formula_enabled) else 'false'
                os.environ['MINERU_TABLE_ENABLE'] = 'true' if bool(current_task.table_enabled) else 'false'
                os.environ['MINERU_VLM_OCR_LANG'] = str(current_task.ocr_lang)
                server_url = os.getenv("VLLM_SERVER_URL", "http://localhost:8000/v1")
                # 注意：OCR语言通过函数参数传递，不是环境变量
                middle_json, infer_result = doc_analyze(
                    pdf_bytes,
                    image_writer=image_writer,
                    backend="http-client",
                    server_url=server_url,
                    language=current_task.ocr_lang,
                    inline_formula_enable=bool(current_task.inline_formula_enabled),
                )

                # 上传图片
                for root, _, files in os.walk(local_image_dir):
                    for file in files:
                        if file.lower().endswith((".png", ".jpg", ".jpeg")):
                            with open(os.path.join(root, file), "rb") as img_f:
                                img_bytes = img_f.read()
                                
                                # 提取图片的RAG元数据
                                # if image_rag_handle:
                                #     try:
                                #         # 使用 RPC 调用，直接传递 bytes
                                #         # 注意：这里为了简单起见使用了同步等待 (ray.get)，如果图片很多可以改为批量异步
                                #         metadata_dict = image_rag_handle.process_image.remote(
                                #             image=img_bytes,
                                #             additional_prompt="<CAPTION>" # 同时获取 Object Detection 结果作为标签来源
                                #         ).result()
                                #         # 将字典转换回对象 (如果 process_image 返回的是 dict)
                                #         # 注意: image_processing_ray.py 返回的是 metadata.to_dict()
                                #         metadata = ImageRAGMetadata(**metadata_dict) if isinstance(metadata_dict, dict) else metadata_dict
                                #         # 存入字典时需要转换为 dict，否则 json.dumps 会失败
                                #         image_rag_metadata_map[file] = metadata.to_dict() if hasattr(metadata, "to_dict") else metadata
                                #     except Exception as e:
                                #         logger.error(f"Image RAG processing failed for {file}: {e}")

                                remote_path = f"{current_task.task_id}/images/{file}"
                                self.minio_tool.upload_file_by_bytes(
                                    bucket_name=current_task.output_bucket,
                                    object_name=remote_path,
                                    file_bytes=img_bytes,
                                    content_type=f"image/{file.split('.')[-1]}"
                                )
                                images_list.append(remote_path)

                # markdown 内容
                pdf_info = middle_json["pdf_info"]
                md_str = vlm_union_make(pdf_info, MakeMode.MM_MD, f"{current_task.task_id}/images")  # ★
                content_list = vlm_union_make(pdf_info, MakeMode.CONTENT_LIST,
                              f"{current_task.task_id}/images")  
                
                clean_md = md_str.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
                # if not current_task.formula_enabled:
                #     clean_md = strip_latex_from_markdown(clean_md)
                self.minio_tool.upload_file_by_bytes(
                    bucket_name=current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}.md",
                    file_bytes=clean_md.encode("utf-8"),
                    content_type="text/markdown"
                )

                # 先试着把image_rag_metadata_map上传到minio
                # self.minio_tool.upload_file_by_bytes(
                #     bucket_name=current_task.output_bucket,
                #     object_name=f"{current_task.task_id}/{name_without_ext}_images.json",
                #     file_bytes=json.dumps(image_rag_metadata_map, ensure_ascii=False, indent=4).encode("utf-8"),
                #     content_type="application/json"
                # )
                
                # 切分处理后的markdown内容，并增强表格标题
                splitted_markdown = process_markdown(clean_md)
                self.minio_tool.upload_file_by_bytes(
                    bucket_name=current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}_splitted.md",
                    file_bytes=splitted_markdown.encode("utf-8"),
                    content_type="text/markdown"
                )

                file_content = json.dumps(content_list, ensure_ascii=False, indent=4).encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
                self.minio_tool.upload_file_by_bytes(
                    bucket_name=current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}_content_list.json",
                    file_bytes=file_content.encode("utf-8"),
                    content_type="application/json"
                )

                # middle_json 内容
                # 如果禁用了公式识别，从JSON结构中移除所有LaTeX表达式
                # if not current_task.formula_enabled:
                #     middle_json = strip_latex_from_json_structure(middle_json)
                
                middle_json_content = json.dumps(middle_json, ensure_ascii=False, indent=4).encode("utf-8","surrogatepass").decode("utf-8","ignore")
                self.minio_tool.upload_file_by_bytes(
                    bucket_name=current_task.output_bucket,
                    object_name=f"{current_task.task_id}/{name_without_ext}_middle.json",
                    file_bytes=middle_json_content.encode("utf-8"),
                    content_type="application/json"
                )

                # 写入任务 output_info
                current_task.output_info = json.dumps({
                    "markdown": f"{current_task.task_id}/{name_without_ext}.md",
                    "content_list": f"{current_task.task_id}/{name_without_ext}_content_list.json",
                    "middle_json": f"{current_task.task_id}/{name_without_ext}_middle.json",
                    "images": images_list,
                    "splitted_markdown": f"{current_task.task_id}/{name_without_ext}_splitted.md"
                })

        except S3Error as e:
            current_task.output_info = str(e)
        except Exception as e:
            logger.exception(e)
            current_task.output_info = str(e)
        finally:
            current_task.finish_time = datetime.datetime.now()
            self.task_repository.update_task(current_task)