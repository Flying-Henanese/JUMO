"""
VLM (Vision-Language Model) 文档处理模块
========================================

本模块实现了基于视觉大模型的文档处理核心逻辑，主要负责将 PDF、Office 文档及图片
转换为结构化的 Markdown 格式。它集成了文档分析、OCR、公式识别、表格提取以及内容重组等功能。

主要功能:
-------------
1.  **多格式支持**:
    -   原生支持 PDF 处理。
    -   支持 Office 文档（Word, Excel）自动转换为 PDF 后处理。
    -   支持图片格式（PNG, JPG 等）自动转换为 PDF 后处理。

2.  **核心处理流程 (`PDFProcessor`)**:
    -   **文件获取**: 从 MinIO 下载源文件。
    -   **预处理**: 将非 PDF 文件（如 Office 文档、图片等）转换为 PDF 字节流。
    -   **文档分析 (`doc_analyze`)**: 调用 MinerU 的混合分析引擎（支持 VLM 后端），
        执行布局分析、OCR、公式识别和表格还原。
    -   **中间态生成**: 生成包含详细布局信息的 `middle.json`。
    -   **内容生成 (`vlm_union_make`)**: 基于分析结果合成 Markdown 内容。

3.  **后处理与存储**:
    -   **图片提取**: 将文档中的图片提取并上传至 MinIO。
    -   **公式清洗**: 可选地从输出中移除 LaTeX 公式（用于纯文本索引场景）。
    -   **Markdown 切分**: 使用 `process_markdown` 对长文档进行语义切分，便于后续 RAG 使用。
    -   **结果持久化**: 将生成的 Markdown 文件和 `middle.json` 上传至 MinIO，并更新任务状态。

4.  **环境配置**:
    -   根据任务参数动态配置 OCR 语言、公式/表格识别开关。
    -   支持通过环境变量配置 VLM 服务地址 (`VLLM_SERVER_URL`)。

使用依赖:
---------
-   `mineru.backend`: 提供底层的文档分析和内容生成能力。
-   `minio_tool`: 处理文件上传下载。
-   `task_repository`: 更新数据库中的任务状态。
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
from mineru.backend.hybrid.hybrid_analyze import doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make

from data.model import Task
from wrapper.logger import log_with_time_consumption
from utils.minio_tool import MinioConnection
from const.file_extensions import OFFICE_EXTENSIONS, PDF_EXTENSIONS,IMAGE_EXTENSIONS,EXCEL_EXTENTIONS
from data.operation import TaskRepository
from processor.markdown_splitter import process_markdown
from processor.converters.file_converters import office_bytes_to_pdf_bytes
from PIL import Image
from processor.converters.markdown_math_stripper import strip_latex_from_json_structure,strip_latex_from_markdown

class PDFProcessor:
    def __init__(self, minio_tool: MinioConnection, task_repository: TaskRepository):
        self.minio_tool: MinioConnection = minio_tool
        self.task_repository: TaskRepository = task_repository
    
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

                local_image_dir, local_md_dir = prepare_env(output_dir, file_name, "auto")
                image_writer, md_writer = FileBasedDataWriter(local_image_dir), FileBasedDataWriter(local_md_dir)

                os.environ['MINERU_VLM_FORMULA_ENABLE'] = 'true' if bool(current_task.formula_enabled) else 'false'
                os.environ['MINERU_VLM_TABLE_ENABLE'] = 'true' if bool(current_task.table_enabled) else 'false'
                os.environ['MINERU_FORMULA_ENABLE'] = 'true' if bool(current_task.formula_enabled) else 'false'
                os.environ['MINERU_TABLE_ENABLE'] = 'true' if bool(current_task.table_enabled) else 'false'
                os.environ['MINERU_VLM_OCR_LANG'] = str(current_task.ocr_lang)
                server_url = os.getenv("VLLM_SERVER_URL", "http://localhost:8000/v1")
                # 注意：OCR语言通过函数参数传递，不是环境变量
                middle_json, infer_result, _ = doc_analyze(
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
                                remote_path = f"{current_task.task_id}/images/{file}"
                                self.minio_tool.upload_file_by_bytes(
                                    bucket_name=current_task.output_bucket,
                                    object_name=remote_path,
                                    file_bytes=img_f.read(),
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