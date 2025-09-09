"""
pdf_route.py

定义 PDF 相关的接口路由，包括分析 PDF 接口和查询任务状态接口。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io
from minio.error import S3Error
from startup import minio_tool
from typing import Optional
from const.file_extensions import WORD_EXTENTIONS,EXCEL_EXTENTIONS
# 为了让接口返回压缩包
import os
import tempfile
from processor.converters.excel_to_markdown import excel_to_markdown
from processor.converters.doc_to_markdown import doc_to_markdown
from processor.markdown_splitter import process_markdown as split_markdown
from pydantic import BaseModel
from fastapi import File, UploadFile
# 实例化资源
router = APIRouter()
UPLOAD_BUCKET = os.getenv('UPLOAD_BUCKET', 'uploads')

class AnalyzeResult(BaseModel):
    markdown_url: str
    markdown_content: str
    images: Optional[list[str]] = None

# 定义接口的返回体
class AnalyzeResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[AnalyzeResult] = None


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
        # 先判断文件是否存在，如果存在则继续后续的分析流程
        if not minio_tool.file_exists(bucket_name=bucket_name, object_name=file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        # 判断文件是excel还是word类型
        file_name, file_ext = os.path.splitext(file_path)
        # 获取文件的字节流
        file_content = minio_tool.get_file_byte(
            bucket_name=bucket_name, 
            object_name=file_path
            )
        markdown_content = ""
        if file_ext in WORD_EXTENTIONS:
            # 分析word文
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=file_ext
            ) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                markdown_content = split_markdown(
                    # 先将word文档转换为markdown
                    doc_to_markdown(
                        input_data = temp_file_path,
                        task_id = file_name,
                        bucket = output_bucket
                        )
                    )
        elif file_ext in EXCEL_EXTENTIONS:
            # 分析excel文件
            markdown_content = ''.join(excel_to_markdown(file_content))
        else:
            raise HTTPException(status_code=400, detail="不支持的文件类型")

        # 上传到minio
        minio_tool.upload_file_by_bytes(
            bucket_name=output_bucket, 
            object_name=f'{file_name}/{file_name}.md', 
            file_bytes=markdown_content.encode('utf-8'),
            content_type='text/markdown'
            )
            
        return AnalyzeResponse(
            status="success",
            message="文件分析完成",
            data=AnalyzeResult(
                markdown_url=f'{file_name}/{file_name}.md',
                markdown_content=markdown_content
            )
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


@router.post("/upload-analyze-office-file")
def upload_analyze_office_file(
    file: UploadFile = File(...),
    header_row_number: int = 1,
    key_columns: list[int] = [1]
):
    try:
        file_name, file_ext = os.path.splitext(file.filename)
        markdown_content = ""

        if file_ext in WORD_EXTENTIONS:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                tmp.write(file.file.read())
                tmp_path = tmp.name  # 临时文件路径
            # 分析word文档
                markdown_content = split_markdown(
                        doc_to_markdown(
                        input_data=tmp_path,  # 传本地路径
                        task_id=file_name,
                        bucket="output"
                    )
                )
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
        md_bytes = io.BytesIO(markdown_content.encode("utf-8"))
        md_bytes.seek(0)

        # 直接返回内存文件
        return StreamingResponse(
            md_bytes,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}.md"'
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
