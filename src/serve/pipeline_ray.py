'''
这个模块还在开发中，用于部署MinerU的分流水线分析。
但是还不是很成熟，这里是把完整的流水线解析过程放到了一个ray serve deployment中。
一个http请求可能会非常长，其实并不太合适，后续还是有很大调整的空间
'''
# src/serve/pipeline_ray.py
from ray import serve
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import numpy as np
import io
import base64

class PipelineRequest(BaseModel):
    images: List[str]  # base64 encoded images
    lang: str = "ch"
    formula_enable: bool = True
    table_enable: bool = True

pipeline_app = FastAPI()

@serve.deployment(
    ray_actor_options={"num_gpus": 0.5},
    autoscaling_config={"min_replicas": 1, "max_replicas": 4}
)
@serve.ingress(pipeline_app)
class PipelineDeployment:
    def __init__(self):
        from mineru.backend.vlm.vlm_analyze import ModelSingleton
        
        # 使用 Hybrid 模式的 ModelSingleton (VLM)
        self.model_manager = ModelSingleton()
        # 预热模型，使用默认配置
        self.model_manager.get_model(backend="transformers")
    
    @pipeline_app.post("/analyze")
    async def analyze(self, request: PipelineRequest | dict):
        # 兼容 Ray Handle 调用传递 dict 的情况
        # 如果未来适用grpc模式，需要在grpc服务中添加对dict的支持
        if isinstance(request, dict):
            request = PipelineRequest(**request)
            
        # 解码图片
        images = []
        for img_str in request.images:
            img_data = base64.b64decode(img_str)
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
            
        # 将图片列表转换为 PDF bytes，以适配 hybrid_analyze 的输入要求
        # 这样做可以利用 hybrid 模式对 PDF 的处理逻辑（如 OCR 自动判断等）
        pdf_bytes_io = io.BytesIO()
        if images:
            images[0].save(pdf_bytes_io, format="PDF", save_all=True, append_images=images[1:])
        pdf_bytes = pdf_bytes_io.getvalue()
        
        # 执行 Hybrid 分析
        from mineru.backend.hybrid.hybrid_analyze import aio_doc_analyze
        
        # 调用 aio_doc_analyze
        # 注意：image_writer 设为 None，这意味着裁剪的图片（公式/表格）不会被保存
        # 如果需要返回这些图片，需要实现自定义的 DataWriter
        middle_json, results, _vlm_ocr_enable = await aio_doc_analyze(
            pdf_bytes=pdf_bytes,
            image_writer=None, 
            predictor=self.model_manager.get_model(backend="transformers"),
            parse_method='auto',
            language=request.lang,
            inline_formula_enable=request.formula_enable,
            # table_enable 参数在 hybrid 中通常由 VLM 自动处理或包含在 formula_enable/kwargs 中
            # hybrid_analyze 签名中似乎没有显式的 table_enable，但可以通过 kwargs 传递给底层
        )
        
        return {
            "middle_json": middle_json,
            "results": results,
            "vlm_ocr_enable": _vlm_ocr_enable
        }

# 定义应用入口
pipeline_app = PipelineDeployment.bind()