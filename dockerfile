# 说明：
# 本 Dockerfile 用于构建一个完整同时精简的文档解析服务镜像
# 使用了二阶构建的技术
# 在第一阶段使用完整的devel版本镜像进行虚拟环境的构建
# 在第二阶段使用精简的runtime版本镜像，同时复制第一阶段构建的虚拟环境，最终生成精简的镜像

# ==========================================
# Stage 1: Builder (构建依赖环境)
# -- 这里主要是为了构建程序运行的环境，并不是最终的镜像环境
# -- 这一阶段的输出物就是.venv目录，包含了程序运行所需的所有依赖
# ==========================================
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

# 非交互式安装软件包，用于构建过程中避免用户交互
ENV DEBIAN_FRONTEND=noninteractive
# 禁用python的缓冲输出，避免在容器中输出时出现延迟
ENV PYTHONUNBUFFERED=1

# 替换 APT 源为阿里云镜像, 加速构建过程
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统构建依赖和 Python 3.12
# Ubuntu 22.04 默认是 Python 3.10，需要添加PPA安装非ubuntu官方版本的Python
# 值得注意的是这里有3个python，分别是python3.12,python3.12-dev和python3.12-venv
# 这三个分别是python解释器、开发头文件（用于编译如numpy和pandas这些库）、虚拟环境模块
# 剩下的是一些构建工具和依赖库，用于编译和安装Python的扩展模块
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
# 因为我们安装的python是一个非常精简的版本，所以需要手动安装pip
# 并配置阿里云镜像源，加速依赖安装过程
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && python3.12 -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 指定工作目录为/app，这是一个常规操作
WORKDIR /app

# 复制 Poetry 配置文件到工作目录
# 准备依赖的安装工作
COPY pyproject.toml poetry.lock ./

# 配置 uv 使用阿里云镜像源，加速依赖安装过程
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 安装 Poetry 并导出 requirements.txt，然后使用 uv 加速安装
# 这里看似复杂，但实际上是结合了poetry管理依赖的优势，以及uv构建环境的速度（反正都是自动化的，我已经操过的心就不用你来了）
# 使用 pip 安装 uv 以避免 GitHub Release 下载被墙的问题
# 还有一个点就是这里让poetry只输出main依赖，避免安装开发过程中使用的ruff和black等工具（这些工具都是开发时使用的，不是运行时依赖）
RUN python3.12 -m pip install --no-cache-dir uv poetry poetry-plugin-export -i https://mirrors.aliyun.com/pypi/simple/

# 先去掉这一步，直接在宿主机poetry lock就好了 
# RUN poetry lock --no-interaction

RUN poetry export --without-hashes --only main --format=requirements.txt > requirements.txt

RUN uv venv .venv --python 3.12

RUN uv pip install --no-cache-dir -r requirements.txt --python .venv --index-url https://mirrors.aliyun.com/pypi/simple/

# ==========================================
# Stage 2: Runner (运行时精简镜像)
# -- 这里要做的是实现真正的运行环境
# -- 这里就是在一个精简镜像的基础上继承上个阶段构建的虚拟环境
# ==========================================
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04 AS runner

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
# 将虚拟环境 bin 目录加入 PATH
# 这个python解释器才是我们最终要使用的(就像你在开发工具上要先选择Python解释器地址一样)
ENV PATH="/app/.venv/bin:$PATH"

# 替换 APT 源为阿里云镜像
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装运行时系统依赖
# LibreOffice和一些相关的汉字语言支持用于文档转换，以及 Python 3.12 运行时
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
#（当时因为这一部分一直出错，为了避免每次docker build都要把所有的apt-get都跑一遍，所以把这部分单独拿出来，每次构建都只重新跑这里）
# 我也是试了非常多次才找到这个最精简的安装方式
# 这里建立了一个软连接，意思就是让所有寻找.so文件的程序转向/usr/lib/x86_64-linux-gnu/libcuda.so.1
# -- 这里看起来有些突兀，为什么突然有一个宿主机上的文件映射到容器中呢？
# -- 这是因为当使用docker run --gpus参数时，宿主机上的nvidia container toolkit会自动挂载宿主机上的cuda驱动到容器中
# -- 所以这里的软连接就是为了让容器中的程序能够找到宿主机上的cuda驱动
RUN apt-get update && apt-get install -y --no-install-recommends \
    cuda-nvcc-12-2 \
    cuda-nvrtc-12-2 \
    cuda-cudart-dev-12-2 \
    && ln -s /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/lib/x86_64-linux-gnu/libcuda.so \
    && rm -rf /var/lib/apt/lists/*

# 安装python-dev，用于编译安装某些 Python 扩展
# 我记得加上这个python-dev是因为vllm在安装时需要编译一些扩展库
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 这里就是二阶构建的精髓，从上个阶段Builder复制虚拟环境
# 除了这个虚拟环境，一阶段的内容不会被复制到运行时镜像中
COPY --from=builder /app/.venv /app/.venv
