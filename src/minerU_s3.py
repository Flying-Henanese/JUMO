from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from minio import Minio
from minio.error import S3Error
import os
import traceback
import json
import io
import uvicorn
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
import dotenv
import tempfile
from magic_pdf.data.data_reader_writer import FileBasedDataWriter
# 加载 .env 文件
dotenv.load_dotenv()
app = FastAPI()

# MinIO 配置
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET_NAME = "miners"
MINIO_SECURE = False
MINIO_OUTPUT_BUCKET = "output"

# 初始化 MinIO 客户端
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

@app.post("/analyze-pdf/")
async def analyze_pdf(pdf_path: str):
    try:
        # 从OSS读取PDF文件
        # pdf_object = minio_client.get_object(MINIO_BUCKET_NAME, pdf_path)
        # pdf_bytes = pdf_object.read()
        with minio_client.get_object(MINIO_BUCKET_NAME, pdf_path) as pdf_object:
            pdf_bytes = pdf_object.read()  # 读取PDF文件的内容为字节流
        
        # 创建数据集实例
        ds = PymuDocDataset(pdf_bytes)

        # 获取文件名（不含扩展名）
        name_without_ext = os.path.splitext(os.path.basename(pdf_path))[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            
            # 判断解析方式并进行推理
            if ds.classify() == SupportedPdfParseMethod.OCR:
                infer_result = ds.apply(doc_analyze, ocr=True)
                pipe_result = infer_result.pipe_ocr_mode()
            else:
                infer_result = ds.apply(doc_analyze, ocr=False)
                pipe_result = infer_result.pipe_txt_mode(FileBasedDataWriter(output_dir))
    
            # 准备输出文件内容
            markdown_content = pipe_result.get_markdown(img_dir_or_bucket_prefix=output_dir)
            content_list = json.dumps(pipe_result.get_content_list(image_dir_or_bucket_prefix=output_dir))
            middle_json = pipe_result.get_middle_json()
    
            # 上传结果到 MinIO
            minio_client.put_object(
                MINIO_OUTPUT_BUCKET,
                f"{name_without_ext}.md",
                io.BytesIO(markdown_content.encode('utf-8')),
                length=len(markdown_content.encode('utf-8')),
                content_type="text/markdown"
            )
    
            minio_client.put_object(
                MINIO_OUTPUT_BUCKET,
                f"{name_without_ext}_content_list.json",
                io.BytesIO(content_list.encode('utf-8')),
                length=len(content_list.encode('utf-8')),
                content_type="application/json"
            )

        minio_client.put_object(
            MINIO_OUTPUT_BUCKET,
            f"{name_without_ext}_middle.json",
            io.BytesIO(middle_json.encode('utf-8')),
            length=len(middle_json.encode('utf-8')),
            content_type="application/json"
        )

        return JSONResponse(content={
            "message": "文件分析成功，结果已上传到 MinIO。",
            "files": [
                f"{name_without_ext}.md",
                f"{name_without_ext}_content_list.json",
                f"{name_without_ext}_middle.json"
            ]
        })

    except S3Error as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=404, detail=f"OSS文件读取失败: {str(e)}")
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"处理文件时出错: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)