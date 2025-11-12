"""
knowledgebase_api_route.py

知识库API路由，提供批量文件分析接口。
"""

from typing import Optional, List
from const.file_extensions import WORD_EXTENTIONS, EXCEL_EXTENTIONS
from .handlers.response_handler import create_success_response,BaseResponse,create_payload_too_large_response
from .handlers.authentication import api_key_required
import os
import tempfile
from datetime import datetime
from processor.converters.excel_to_markdown import excel_to_markdown
from processor.converters.doc_to_markdown import doc_to_markdown
from processor.markdown_splitter import process_markdown as split_markdown
from pydantic import BaseModel, Field
from fastapi import APIRouter, BackgroundTasks
from minio.error import S3Error
from const.ocr_lang_enum import OCRLanguage
from data.model import Task
from utils.id_generator import generate_short_uuid
from const.task_status_enum import TaskStatus
from processor.tasking.pdf_task import process_pdf_task
from startup import task_repository,minio_tool

# 实例化资源，添加统一前缀
router = APIRouter(prefix="/knowledgebase")
# 最大同时处理的任务数
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 8))
# 最大排队任务数
MAX_QUEUING_TASKS = int(os.getenv('MAX_QUEUING_TASKS', 20))
# 默认知识库存储桶
DEFAULT_KNOWLEDGEBASE_BUCKET = os.getenv('DEFAULT_KNOWLEDGEBASE_BUCKET', 'xt-0116')

class PDFResponseInfo(BaseModel):
    fileId:str = Field(..., description="文件唯一标识", example="file_123")
    taskId:str = Field(..., description="任务唯一标识", example="task_123")

class TaskStatusResponse(BaseModel):
    """批量获取任务状态响应模型"""
    taskId: str = Field(..., description="任务唯一标识", example="task_123")
    status: TaskStatus = Field(..., description="任务状态", example=TaskStatus.PROCESSING)
    processedOssName: Optional[str] = Field(None, description="处理后的文件在OSS上的路径", example="processed/2025/09/manual.md")
    message: Optional[str] = Field(None, description="任务状态消息", example="任务正在处理")

class FileInfo(BaseModel):
    """文件信息模型"""
    fileId: str = Field(..., description="文件唯一标识", example="file_123")
    ossName: str = Field(..., description="MinIO中的对象名称", example="documents/2025/09/report.docx")

class BatchAnalyzeRequest(BaseModel):
    """批量分析请求模型"""
    ossInfo: List[FileInfo] = Field(..., description="文件信息列表，包含文件表示fileid和原始文件在OSS上的路径", example=[
        {"fileId": "file_123", "ossName": "documents/2025/09/report.docx"},
        {"fileId": "file_456", "ossName": "documents/2025/09/data.xlsx"}
    ])
    paragraphMaxLength: Optional[int] = Field(None, description="段落最大长度(单位:字符数)", example=1000)
    preserveSmartTags: Optional[bool] = Field(None, description="是否保留智能标签", example=True)

# 批量实时分析响应类型
BatchAnalyzeResponse = BaseResponse[List[FileInfo]]
# 批量异步分析响应类型
BatchPDFAnalyzeResponse = BaseResponse[List[PDFResponseInfo]]
# 批量获取任务状态响应模型
BatchTaskStatusResponse = BaseResponse[List[TaskStatusResponse]]


# 批量分析文档文件接口，实时响应
@router.post("/analyze-document-files", response_model=BatchAnalyzeResponse)
@api_key_required
def analyze_document_files(
    request: BatchAnalyzeRequest
) -> BatchAnalyzeResponse:
    """
    批量分析Word和Excel文件的接口
    请求格式: { "files": [{"fileId": "file_123", "ossName": "path/to/file.docx"}], ... }
    返回格式: { "code": 200, "message": "Success", "data": [{"fileId": "file_123", "ossName": "path/to/file.md"}] }
    """
    results: List[FileInfo] = []
    if len(request.ossInfo) > 10:
        # 传入的文件过多
        return create_payload_too_large_response()
    for file_info in request.ossInfo:
        try:
            result = process_single_file(
                file_info=file_info,
                bucket_name=DEFAULT_KNOWLEDGEBASE_BUCKET,
                output_bucket=DEFAULT_KNOWLEDGEBASE_BUCKET,
                max_paragraph_length=request.paragraphMaxLength or 1000,
                preserve_smart_tags=request.preserveSmartTags or True
            )
            results.append(result)
        except Exception as e:
            # 单个文件处理失败，记录错误信息，返回原始的FileInfo对象
            results.append(FileInfo(
                fileId=file_info.fileId,
                ossName=f"处理失败: {str(e)}"
            ))
    
    # 检查是否有失败的文件
    failed_files = [r for r in results if "处理失败" in r.ossName]
    if failed_files:
        error_message = f"成功处理 {len(results) - len(failed_files)} 个文件，失败 {len(failed_files)} 个文件"
        return create_success_response(results, error_message)
    else:
        return create_success_response(results, f"成功处理 {len(results)} 个文件")

@router.post("/analyze-pdf")
@api_key_required
async def analyze_pdf(
    background_tasks: BackgroundTasks, 
    request: BatchAnalyzeRequest
) -> BatchPDFAnalyzeResponse:
    """
    分析PDF文件的接口
    """
    # 第一步：检查系统负载，如果活动任务数量超过最大值，直接返回错误
    if task_repository.count_active_task() >= MAX_QUEUING_TASKS:
        return create_payload_too_large_response(
            message=f"系统繁忙，当前队列已满（{MAX_QUEUING_TASKS}个任务），请稍后再试"
        )
    
    results: List[PDFResponseInfo] = []
    if len(request.ossInfo) > 10:
        # 传入的文件过多
        return create_payload_too_large_response(message="传入的文件过多，最多支持10个文件")
    for file_info in request.ossInfo:
        # 先检查是否存在文件
        try:
            minio_tool.file_exists(bucket_name=DEFAULT_KNOWLEDGEBASE_BUCKET, object_name=file_info.ossName)
        except S3Error as e:
            results.append(PDFResponseInfo(
                fileId=file_info.fileId,
                taskId="",
                message=str(e)
            ))
            continue

        task_id = generate_short_uuid()
        
        task_to_add = Task(
            task_id=task_id,
            object_key=file_info.ossName,
            bucket_name=DEFAULT_KNOWLEDGEBASE_BUCKET,
            output_bucket=DEFAULT_KNOWLEDGEBASE_BUCKET,
            ocr_enabled=True,
            table_enabled=True,
            formula_enabled=True,
            ocr_lang=OCRLanguage.get_default().value,
            output_info='',
            create_time=datetime.now(),
            finish_time=None,
        )

        # 先创建任务响应对象
        result_info = PDFResponseInfo(
            fileId=file_info.fileId,
            taskId=task_id,
            message=""
        )
        results.append(result_info)
        
        # 然后检查队列状态
        if task_repository.count_processing_task() < MAX_WORKERS:
            active_task.status = TaskStatus.PROCESSING
        elif task_repository.count_active_task() >= MAX_QUEUING_TASKS:
            return create_success_response(
                data=results, 
                message=f"队列已满，成功生成{len(results)}份文档处理任务，剩余文件请稍后处理"
            )
        task_repository.create_task(task_to_add)
        active_task = task_repository.create_active_task(active_task)
        background_tasks.add_task(process_pdf_task, task_to_add)

    return create_success_response(data=results,message=f"成功生成{len(results)}份pdf文档处理任务")

@router.post("/batch-task-status", response_model=BatchTaskStatusResponse)
@api_key_required
async def get_batch_task_status(taskIds: List[str]) -> BatchTaskStatusResponse:
    """
    批量获取任务状态接口
    :param taskIds: 任务ID列表
    :return: 包含所有任务状态的列表
    """
    results = []
    
    for task_id in taskIds:
        active_task = task_repository.get_active_task(task_id)
        if active_task:
            results.append(TaskStatusResponse(
                taskId=active_task.task_id,
                status=active_task.status,
                message="任务正在处理" if active_task.status == TaskStatus.PROCESSING else "任务已加入队列"
            ))
            continue
            
        task = task_repository.get_task_by_id(task_id)
        if task:
            results.append(TaskStatusResponse(
                taskId=task.task_id,
                status=TaskStatus.COMPLETED,
                processedOssName=task.output_info
            ))
        else:
            results.append(TaskStatusResponse(
                taskId=task_id,
                status="not_found",
                message="任务不存在"
            ))
    
    return create_success_response(data=results)
        

def process_single_file(
    file_info: FileInfo,
    bucket_name: str,
    output_bucket: str,
    max_paragraph_length: int,
    preserve_smart_tags: bool
) -> FileInfo:
    """处理单个文件，返回FileInfo对象"""
    try:
        # 判断文件是否存在
        if not minio_tool.file_exists(bucket_name=bucket_name, object_name=file_info.ossName):
            return FileInfo(
                fileId=file_info.fileId,
                ossName="文件不存在"
            )
        
        # 获取文件扩展名
        _, file_ext = os.path.splitext(file_info.ossName)
        
        # 获取文件的字节流
        file_content = minio_tool.get_file_byte(
            bucket_name=bucket_name, 
            object_name=file_info.ossName
        )
        
        markdown_content = ""
        
        if file_ext in WORD_EXTENTIONS:
            # 分析word文档
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                markdown_content = split_markdown(
                    doc_to_markdown(
                        input_data=temp_file_path,
                        task_id=file_info.fileId,
                        bucket=output_bucket
                    ),
                    max_length=max_paragraph_length
                )
        elif file_ext in EXCEL_EXTENTIONS:
            # 分析excel文件
            markdown_content = ''.join(excel_to_markdown(file_content))
        else:
            return FileInfo(
                fileId=file_info.fileId,
                ossName="不支持的文件类型"
            )

        # 生成输出文件名，使用当日日期
        current_date = datetime.now().strftime("%Y%m%d")
        output_filename = f"{current_date}/{file_info.fileId}.md"
        
        # 上传到minio
        minio_tool.upload_file_by_bytes(
            bucket_name=output_bucket, 
            object_name=output_filename, 
            file_bytes=markdown_content.encode('utf-8'),
            content_type='text/markdown'
        )
        
        # 返回处理成功的FileInfo对象，ossName字段包含生成的markdown文件路径
        return FileInfo(
            fileId=file_info.fileId,
            ossName=output_filename
        )
        
    except S3Error as e:
        return FileInfo(
            fileId=file_info.fileId,
            ossName=f"MinIO错误: {str(e)}"
        )
    except Exception as e:
        return FileInfo(
            fileId=file_info.fileId,
            ossName=f"处理文件时出错: {str(e)}"
        )
