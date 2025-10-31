# 批量PDF处理脚本使用说明

## 功能概述

这个脚本用于批量处理PDF文档，通过调用mineru-service的API接口实现以下功能：

1. 自动上传PDF文件并启动分析任务
2. 定期检查任务状态（默认每10秒检查一次）
3. 任务完成后自动下载处理结果
4. 记录失败的任务信息到日志
5. 支持断点续传功能

## 使用方法

### 1. 准备工作

1. 确保mineru-service服务已启动并运行在指定地址（默认为http://localhost:8000）
2. 创建一个目录存放要处理的PDF文件（默认为./pdfs）
3. 创建一个目录用于存放处理结果（默认为./results）

### 2. 基本使用

```bash
# 使用默认参数运行脚本
python batch_pdf_processor.py

# 或者指定自定义参数
python batch_pdf_processor.py --api-url http://your-server:8000 --input-dir /path/to/pdfs --output-dir /path/to/results
```

### 3. 参数说明

- `--api-url`: API基础URL，默认为http://localhost:8000
- `--input-dir`: PDF文件输入目录，默认为./pdfs
- `--output-dir`: 结果输出目录，默认为./results
- `--interval`: 状态检查间隔（秒），默认为10秒
- `--max-retries`: 最大重试次数，默认为3次

### 4. 断点续传

脚本支持断点续传功能。如果处理过程中断，再次运行脚本时会：

1. 读取之前保存的处理状态
2. 跳过已成功处理的文件
3. 继续处理剩余的文件

处理状态保存在输出目录的`processing_status.json`文件中。

### 5. 日志文件

脚本运行时会生成日志文件`batch_pdf_processor.log`，记录：

- 处理进度
- 成功/失败的任务信息
- 错误详情

## 工作流程

1. 扫描输入目录中的所有PDF文件
2. 对于每个文件：
   - 上传文件并启动分析任务
   - 定期检查任务状态（每10秒）
   - 任务完成后下载结果
   - 如果失败，记录错误信息并重试（最多3次）
3. 所有文件处理完成后，输出处理结果摘要

## 注意事项

1. 确保网络连接稳定，避免上传/下载过程中断
2. 根据服务器性能和处理时间，适当调整状态检查间隔
3. 大量文件处理可能需要很长时间，建议在稳定环境中运行
4. 定期检查日志文件，及时发现和处理问题

## 示例

```bash
# 处理当前目录下pdfs文件夹中的所有PDF文件
mkdir -p pdfs results
cp your_pdf_files/*.pdf pdfs/
python batch_pdf_processor.py --input-dir ./pdfs --output-dir ./results --interval 15
```