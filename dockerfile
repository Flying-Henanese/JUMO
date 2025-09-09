# 如果使用NVIDIA的GPU环境，则换成使用这个镜像
FROM nvidia/cuda:12.2.0-base-ubuntu22.04
#在ubuntu基础上安装Python 3.12
# 安装Python和LibreOffice
RUN apt-get update && apt-get install -y python3.12 python3-pip libreoffice

# 使用官方Python 3.12基础镜像
# FROM python:3.12-slim

# 安装Poetry
RUN pip install --no-cache-dir poetry
# 安装中文支持，解决libre office中遇到的转换中文内容的问题
RUN sudo apt update && \
    sudo apt install -y language-pack-zh-hans \
                       fonts-wqy-microhei \
                       fonts-wqy-zenhei \
                       libreoffice-l10n-zh-cn && \
    sudo update-locale LANG=zh_CN.UTF-8 && \
    sudo apt clean
# 这里要添加一步安装RUST编译器
RUN apt-get update && apt-get install -y rustc cargo
# 还要安装OPENSSL开发库
RUN apt-get update && apt-get install -y libssl-dev pkg-config

# 设置工作目录
WORKDIR /app

# 配置Poetry在项目目录中创建虚拟环境
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true

# 复制项目文件
COPY pyproject.toml poetry.lock ./

# 安装项目依赖
RUN poetry install --no-dev --no-interaction --no-ansi


# 复制其余项目文件
COPY . .

# 设置环境变量
ENV MINERU_MODEL_SOURCE=modelscope
ENV CUDA_VISIBLE_DEVICES=0,1,2,3
ENV HF_ENDPOINT=https://hf-mirror.com
# 在这设置mineru使用过哪个GPU，vlm模式在sglang_server_restart启动脚本设置
ENV MINERU_DEVICE_MODE=cuda:0
# 语义切分模型所使用的GPU设备编号
ENV DEFAULT_CUDA_DEVICE=0

# 暴露端口
EXPOSE 8000

# 启动命令（使用虚拟环境中的Python）
# 启动sglang服务（后台运行）
RUN nohup /app/.venv/bin/mineru-sglang-server --port 30000 --model-path "OpenDataLab/MinerU2.0-2505-0.9B" > /app/mineru_sglang_server.log 2>&1 &

# 启动主服务
CMD ["/app/.venv/bin/python", "src/mineru_service.py"]