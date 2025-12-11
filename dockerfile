# ==========================================
# Stage 1: Builder (构建依赖环境)
# ==========================================
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 替换 APT 源为阿里云镜像加速构建
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统构建依赖和 Python 3.12
# Ubuntu 22.04 默认是 Python 3.10，需要添加 PPA 安装 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    git \
    build-essential \
    rustc \
    cargo \
    libssl-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 pip 并配置 PyPI 镜像
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && python3.12 -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

# 复制 Poetry 配置文件
COPY pyproject.toml poetry.lock ./

# 配置 uv 使用阿里云镜像源
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 安装 Poetry 并导出 requirements.txt，然后使用 uv 加速安装
# uv 是一个极速的 Python 包管理器，能显著加快依赖安装速度
# 使用 pip 安装 uv 以避免 GitHub Release 下载被墙的问题
RUN python3.12 -m pip install --no-cache-dir uv poetry poetry-plugin-export -i https://mirrors.aliyun.com/pypi/simple/ \
    && poetry export --without-hashes --only main --format=requirements.txt > requirements.txt \
    && uv venv .venv --python 3.12 \
    && uv pip install --no-cache-dir -r requirements.txt --python .venv --index-url https://mirrors.aliyun.com/pypi/simple/

# ==========================================
# Stage 2: Runner (运行时精简镜像)
# ==========================================
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04 AS runner

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
# 将虚拟环境 bin 目录加入 PATH
ENV PATH="/app/.venv/bin:$PATH"

# 替换 APT 源为阿里云镜像
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装运行时系统依赖
# LibreOffice 用于文档转换，以及 Python 3.12 运行时
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    libreoffice \
    language-pack-zh-hans \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    libreoffice-l10n-zh-cn \
    curl \
    libgl1 \
    gcc \
    g++ \
    libglib2.0-0 \
    && update-locale LANG=zh_CN.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# 单独安装 CUDA 组件，方便利用其他层的缓存
RUN apt-get update && apt-get install -y --no-install-recommends \
    cuda-nvcc-12-2 \
    cuda-nvrtc-12-2 \
    cuda-cudart-dev-12-2 \
    && ln -s /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/lib/x86_64-linux-gnu/libcuda.so \
    && rm -rf /var/lib/apt/lists/*

    # 安装python-dev，用于编译安装某些 Python 扩展
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

# 从 Builder 阶段复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 复制项目代码
COPY . .

# 赋予脚本可执行权限
RUN chmod +x manage_services.sh src/celery_worker/*.sh *.sh

# 预先下载 NLTK 数据 (punkt_tab)，使用国内镜像加速
# (还是使用卷挂载吧，每次构建下载太慢了)
# RUN /app/.venv/bin/python -c "import nltk; nltk.downloader.Downloader.INDEX_URL = 'https://raw.gitmirror.com/nltk/nltk_data/gh-pages/index.xml'; nltk.download('punkt_tab')"

# 设置环境变量默认值
# 从modelscope获取Mineru的模型
ENV MINERU_MODEL_SOURCE=modelscope
# 让 vLLM 也使用 ModelScope 下载/加载模型(其实在vLLM的启动脚本中已经默认开启了)
ENV VLLM_USE_MODELSCOPE=True
# 从huggingface镜像站获取模型
ENV HF_ENDPOINT=https://hf-mirror.com
ENV API_SERVICE_PORT=5116
# 暴露端口
EXPOSE ${API_SERVICE_PORT} 30000

# 设置 Python 和 Celery 的执行路径 (Docker 环境)
ENV PYTHON_PATH=/app/.venv/bin/python
ENV CELERY_PATH=/app/.venv/bin/celery
# 将 src 目录加入 PYTHONPATH，确保 Python 能正确解析包结构
ENV PYTHONPATH=/app/src

# 声明挂载点，以便在运行时挂载宿主机缓存目录
# 这样可以复用宿主机的模型缓存，避免重复下载
VOLUME ["/root/.cache/huggingface", "/root/.cache/modelscope", "/root/.cache/vllm", "/root/nltk_data"]

# 启动命令
CMD ["bash", "manage_services.sh", "start"]