import os
from typing import AsyncGenerator, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
import ray
from ray import serve
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.entrypoints.openai.protocol import (
    ChatCompletionRequest,
    ErrorResponse,
)
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat
from vllm.utils import random_uuid

# Define the FastAPI app
app = FastAPI()

@serve.deployment(
    ray_actor_options={"num_gpus": 1},
    autoscaling_config={"min_replicas": 1, "max_replicas": 4}, # 根据实际 GPU 数量调整
)
@serve.ingress(app)
class VLLMDeployment:
    def __init__(self):
        # Load args from env or defaults
        self.model = os.getenv("MODEL", "opendatalab/MinerU2.5-2509-1.2B")
        tensor_parallel_size = int(os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "1"))
        gpu_memory_utilization = float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.9"))
        
        # Parse arguments
        engine_args = AsyncEngineArgs(
            model=self.model,
            tensor_parallel_size=tensor_parallel_size,
            gpu_memory_utilization=gpu_memory_utilization,
            trust_remote_code=True,
            disable_log_requests=True,
        )
        
        # Initialize Engine
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        
        # Initialize OpenAI Serving Chat
        # Note: This initialization pattern matches vLLM 0.4.x+
        try:
            model_config = self.engine.get_model_config()
            served_model_names = [self.model]
            self.openai_serving_chat = OpenAIServingChat(
                self.engine, 
                model_config, 
                served_model_names, 
                response_role="assistant"
            )
        except Exception as e:
            print(f"Failed to initialize OpenAIServingChat: {e}")
            raise e

    @app.post("/v1/chat/completions")
    async def create_chat_completion(self, request: ChatCompletionRequest, raw_request: Request):
        """
        OpenAI-compatible chat completion endpoint.
        """
        # Ensure model name matches or is default
        if not request.model:
            request.model = self.model
            
        generator = await self.openai_serving_chat.create_chat_completion(
            request, raw_request
        )
        
        if isinstance(generator, ErrorResponse):
             return JSONResponse(content=generator.model_dump(), status_code=generator.code)
        
        if request.stream:
            return StreamingResponse(content=generator, media_type="text/event-stream")
        else:
            return JSONResponse(content=generator.model_dump())

    @app.get("/health")
    async def health(self):
        return {"status": "ok"}

# Bind the deployment
deployment = VLLMDeployment.bind()


# 确保安装了 ray[serve]
# pip install "ray[serve]"
# serve run src.serve.vllm_ray:deployment


# export USE_REMOTE_VLLM=true
# export VLLM_SERVER_URL="http://localhost:8000/v1"
# # 可选：控制并发数，默认是 CPU 核数的一半
# export CELERY_WORKER_CONCURRENCY=10 

# python src/celery_worker/pdf_process_worker.py