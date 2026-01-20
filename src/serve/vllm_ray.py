import os
import ray
from ray import serve
from ray.serve.llm import LLMConfig, build_openai_app

# Load configuration from environment variables
tensor_parallel_size = int(os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "1"))
gpu_memory_utilization = float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.6"))
cpu_per_instance = float(os.getenv("VLLM_CPU_PER_INSTANCE", "4"))
dtype = os.getenv("VLLM_DTYPE", "auto")
model = os.getenv("MODEL", "opendatalab/MinerU2.5-2509-1.2B")

# Configure the LLM
llm_config = LLMConfig(
    model_loading_config={
        "model_id": model,
    },
    engine_kwargs={
        "trust_remote_code": True,  # Required for MinerU2.5
        "tensor_parallel_size": tensor_parallel_size,
        "gpu_memory_utilization": gpu_memory_utilization,
        "max_model_len": 16384,
        "dtype": dtype,
        "limit_mm_per_prompt": {"image": 10},  # Prevent OOM with multiple images
    },
    deployment_config={
        "autoscaling_config": {
            "min_replicas": 1,
            "max_replicas": 4,
            "target_ongoing_requests": 20,
        },
        "ray_actor_options": {
            "num_cpus": cpu_per_instance
        },
    },
)

# Build OpenAI-compatible application
# The paths will automatically be prefixed (e.g., /v1/chat/completions)
app = build_openai_app({"llm_configs": [llm_config]})

# Bind the deployment for Ray Serve CLI
deployment = app

# 确保安装了 ray[serve]
# pip install "ray[serve]"
# serve run src.serve.vllm_ray:deployment


# export USE_REMOTE_VLLM=true
# export VLLM_SERVER_URL="http://localhost:8000/v1"
# # 可选：控制并发数，默认是 CPU 核数的一半
# export CELERY_WORKER_CONCURRENCY=10 

# python src/celery_worker/pdf_process_worker.py