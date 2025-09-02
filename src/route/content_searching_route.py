from fastapi import APIRouter
from processor.content_indexing import DocumentIndexService
from utils.minio_tool import MinioConnection
from fastapi import HTTPException
from fastapi import Depends
from loguru import logger
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
content_indexing_service = DocumentIndexService()
minio_tool = MinioConnection()

class SearchResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[dict] = None

@router.post("/search_pave")
def search_pave(task_id: str, 
                   bucket_name: str,
                   minio_tool: MinioConnection = Depends()):
    if not minio_tool.list_objects(bucket_name=bucket_name,prefix=f"{task_id}/",recursive=False):
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        content_indexing_service.load_document_index_from_oss(task_id, bucket_name)
    except FileNotFoundError:
        logger.error(f"索引文件不存在，task_id: {task_id}, bucket_name: {bucket_name}")
        raise HTTPException(status_code=404, detail="索引文件不存在")
    return SearchResponse(
        status="success",
        message="索引构建成功",
        data={   
        }
    )


@router.get("/content_search")
def content_search(task_id: str,
                   keyword: str):
    try:
        result = content_indexing_service.search_keyword_in_document(task_id, keyword)
        return SearchResponse(
            status="success",
            message="搜索成功",
            data={
                "result": result
            }
        )
    except Exception as e:
        logger.error(f"搜索失败，task_id: {task_id}, keyword: {keyword}, error: {e}")
        raise HTTPException(status_code=500, detail="搜索失败")