"""
pdf_route.py

定义 PDF 相关的接口路由，包括分析 PDF 接口和查询任务状态接口。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io
from minio.error import S3Error
from startup import minio_tool
from typing import Optional, List
from const.file_extensions import WORD_EXTENTIONS,EXCEL_EXTENTIONS
# 为了让接口返回压缩包
import os
import tempfile
from processor.converters.excel_to_markdown import excel_to_markdown
from processor.converters.doc_to_markdown import doc_to_markdown
from processor.markdown_splitter import process_markdown as split_markdown
from pydantic import BaseModel
from loguru import logger
from fastapi import File, UploadFile, Form
import urllib.parse
import json
from utils.id_generator import generate_short_uuid


def ensure_utf8_string(content) -> str:
    """确保内容是UTF-8字符串"""
    if isinstance(content, bytes):
        return content.decode('utf-8', errors='replace')
    elif isinstance(content, str):
        try:
            content.encode('utf-8')
            return content
        except UnicodeEncodeError:
            return content.encode('latin-1', errors='ignore').decode('utf-8', errors='replace')
    return str(content)


def safe_filename_for_header(filename: str) -> str:
    """为HTTP头部生成安全的文件名"""
    try:
        filename.encode('ascii')
        return f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        encoded_filename = urllib.parse.quote(filename, safe='')
        return f"attachment; filename*=UTF-8''{encoded_filename}"
# 实例化资源
router = APIRouter(prefix="/realtime")
UPLOAD_BUCKET = os.getenv('UPLOAD_BUCKET', 'uploads')

class AnalyzeResult(BaseModel):
    markdown_content: str
    raw_markdown_url: Optional[str] = None
    split_markdown_url: Optional[str] = None
    raw_markdown_content: Optional[str] = None
    split_markdown_content: Optional[str] = None
    images: Optional[List[str]] = None

# 定义接口的返回体
class AnalyzeResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[AnalyzeResult] = None

@router.post("/split-markdown-file")
def split_markdown_file(
    markdown_content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """
    分割markdown文件的接口
    """
    result = ""
    if markdown_content and len(markdown_content) > 0:
        result = split_markdown(md_text = markdown_content)
    elif file:
        result = ensure_utf8_string(file.file.read().decode('utf-8', errors='replace'))
        result = split_markdown(result)
    else:
        raise HTTPException(status_code=400, detail="请提供markdown文件或者非空markdown内容")

    return AnalyzeResponse(
        status="success",
        message="文件已成功分析",
        data=AnalyzeResult(
            markdown_content=result,
            split_markdown_content=result,
            images=None
        )
    )

@router.post("/analyze-office-file")
def analyze_document(
    file_path: str,
    bucket_name: str,
    output_bucket: str,
    processing_type: str = "0",
    max_heading_chunk_size: int = 1024,
    fallback_chunk_size: int = 1024
):
    """
    分析word和excel文件的接口
    """
    try:
        if not minio_tool.bucket_exists(output_bucket):
            raise HTTPException(status_code=400, detail=f"输出存储桶{output_bucket}不存在")
        if not minio_tool.file_exists(bucket_name=bucket_name, object_name=file_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        original_filename = os.path.basename(file_path)
        original_name_without_ext, file_ext = os.path.splitext(original_filename)
        file_ext = file_ext.lower()
        file_content = minio_tool.get_file_byte(bucket_name=bucket_name, object_name=file_path)

        result_dir = generate_short_uuid()
        raw_markdown = ""
        split_markdown_content = ""
        images: Optional[List[str]] = []

        if file_ext in WORD_EXTENTIONS:
            temp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                raw_markdown, images = doc_to_markdown(
                    input_data=temp_file_path,
                    task_id=result_dir,
                    bucket=output_bucket,
                    return_images=True
                )
            finally:
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            raw_markdown = ensure_utf8_string(raw_markdown)
            split_markdown_content = split_markdown(raw_markdown)
        elif file_ext in EXCEL_EXTENTIONS:
            raw_markdown = ensure_utf8_string(''.join(excel_to_markdown(file_content)))
            split_markdown_content = split_markdown(raw_markdown)
        else:
            raise HTTPException(status_code=400, detail="不支持的文件类型")

        split_markdown_content = ensure_utf8_string(split_markdown_content)

        raw_markdown_url = f'{result_dir}/{original_name_without_ext}.md'
        split_markdown_url = f'{result_dir}/{original_name_without_ext}_splitted.md'

        minio_tool.upload_file_by_bytes(
            bucket_name=output_bucket,
            object_name=raw_markdown_url,
            file_bytes=raw_markdown.encode('utf-8'),
            content_type='text/markdown; charset=utf-8'
        )
        minio_tool.upload_file_by_bytes(
            bucket_name=output_bucket,
            object_name=split_markdown_url,
            file_bytes=split_markdown_content.encode('utf-8'),
            content_type='text/markdown; charset=utf-8'
        )

        result = {
            "markdown": raw_markdown_url,
            "splitted_markdown": split_markdown_url,
            "images": images or []
        }
        return {
            "task_id": result_dir,
            "status": "COMPLETED",
            "result": json.dumps(result, ensure_ascii=False)
        }
    except HTTPException:
        raise
    except S3Error as e:
        return {
            "task_id": "",
            "status": "FAILED",
            "result": None,
            "message": f"MinIO错误: {str(e)}"
        }
    except Exception as e:
        return {
            "task_id": "",
            "status": "FAILED",
            "result": None,
            "message": f"处理文件时出错: {str(e)}"
        }

@router.post("/analyze-office-dir")
def analyze_office_dir(
    dir_path: str,
    bucket_name: str,
    output_bucket: str,
    processing_type: str = "0",
    max_heading_chunk_size: int = 1024,
    fallback_chunk_size: int = 1024
):
    try:
        objects = minio_tool.list_objects(bucket_name=bucket_name, prefix=dir_path, recursive=True)
        if not objects:
            raise HTTPException(status_code=404, detail="目录下没有文件")
        results = []
        for obj in objects:
            file_name, file_ext = os.path.splitext(obj)
            file_name = file_name.split('/')[-1]
            if (file_ext not in WORD_EXTENTIONS) and (file_ext not in EXCEL_EXTENTIONS) and (file_ext != ".doc"):
                continue
            file_content = minio_tool.get_file_byte(bucket_name=bucket_name, object_name=obj)
            if file_ext == ".doc":
                from processor.converters.file_converters import office_bytes_to_docx_bytes
                # 先将 .doc 转换为 .docx
                docx_bytes = office_bytes_to_docx_bytes(file_content, suffix=file_ext)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
                    temp_file.write(docx_bytes)
                    temp_file_path = temp_file.name
                raw_markdown = doc_to_markdown(input_data=temp_file_path, task_id=file_name, bucket=output_bucket)
                raw_markdown = ensure_utf8_string(raw_markdown)
                markdown_content = split_markdown(raw_markdown)
                os.remove(temp_file_path)
            elif file_ext in WORD_EXTENTIONS:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                raw_markdown = doc_to_markdown(input_data=temp_file_path, task_id=file_name, bucket=output_bucket)
                raw_markdown = ensure_utf8_string(raw_markdown)
                markdown_content = split_markdown(raw_markdown)
                os.remove(temp_file_path)
            else:
                # 处理 Excel，包括 CSV
                is_csv = (file_ext.lower() == ".csv")
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                markdown_content = ''.join(excel_to_markdown(
                    excel_content=temp_file_path,
                    file_name=file_name,
                    is_csv=is_csv,
                ))
                os.remove(temp_file_path)
            markdown_content = ensure_utf8_string(markdown_content)
            markdown_bytes = markdown_content.encode('utf-8')
            out_object = f"{file_name}/{file_name}.md"
            minio_tool.upload_file_by_bytes(
                bucket_name=output_bucket,
                object_name=out_object,
                file_bytes=markdown_bytes,
                content_type='text/markdown; charset=utf-8'
            )
            results.append({"source": obj, "markdown_url": out_object})
        return {
            "status": "success",
            "message": f"共处理 {len(results)} 个文件",
            "data": results
        }
    except S3Error as e:
        return {
            "status": "error",
            "message": f"MinIO错误: {str(e)}",
            "data": None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"处理目录时出错: {str(e)}",
            "data": None
        }


@router.post("/upload-analyze-office-file")
def upload_analyze_office_file(
    file: UploadFile = File(...),
    header_row_number: int = 1,
    key_columns: List[int] = [1]
):
    try:
        file_name, file_ext = os.path.splitext(file.filename)
        markdown_content = ""

        if file_ext in WORD_EXTENTIONS:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                tmp.write(file.file.read())
                tmp_path = tmp.name  # 临时文件路径
            # 分析word文档
                # 获取markdown内容
                raw_markdown = doc_to_markdown(
                    input_data=tmp_path,  # 传本地路径
                    task_id=file_name,
                    bucket="output"
                )
                raw_markdown = ensure_utf8_string(raw_markdown)
                markdown_content = split_markdown(raw_markdown)
            os.remove(tmp_path)
        elif file_ext in EXCEL_EXTENTIONS:
            markdown_content = ''.join(excel_to_markdown(
                excel_content=file.file,
                file_name=file_name,
                is_csv=file_ext == '.csv',
                header_row_number=header_row_number,
                key_columns=key_columns
            ))
        else:
            raise HTTPException(status_code=400, detail="不支持的文件类型")

        # 将 Markdown 内容写到内存中
        markdown_content = ensure_utf8_string(markdown_content)
        markdown_bytes = markdown_content.encode('utf-8')
        md_bytes = io.BytesIO(markdown_bytes)
        md_bytes.seek(0)

        # 直接返回内存文件
        content_disposition = safe_filename_for_header(f"{file_name}.md")
        
        return StreamingResponse(
            md_bytes,
            media_type="text/markdown",
            headers={
                "Content-Disposition": content_disposition
            }
        )

    except S3Error as e:
        return AnalyzeResponse(
            status="error",
            message=f"MinIO错误: {str(e)}",
            data=None
        )
    except Exception as e:
        return AnalyzeResponse(
            status="error",
            message=f"处理文件时出错: {str(e)}",
            data=None
        )
