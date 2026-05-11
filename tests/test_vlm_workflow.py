import os
import re
import tempfile
import sys
from pathlib import Path
from loguru import logger

# 确保可以导入 src 下的模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mineru.backend.hybrid.hybrid_analyze import doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make
from mineru.utils.enum_class import MakeMode
from mineru.cli.common import prepare_env
from wrapper.mineru_image_writer_wrapper import MyImageInterceptor

"""
测试 VLM 模式下的 PDF 解析及图片描述生成流程。
借鉴了 omnidocbench_parse.py 的本地执行方式，并提取了 vlm_mode.py 中的核心逻辑。
"""

def get_test_pdf_path(input_path=None):
    """
    获取测试 PDF 路径。
    优先级：手动传入 > 环境变量 > 默认路径 > 自动搜索
    """
    if input_path:
        return input_path

    path = os.getenv("TEST_PDF_PATH", "/app/data/input/test.pdf")
    if os.path.exists(path):
        return path
    
    # 尝试在项目目录下找一个 pdf
    pdfs = list(Path(PROJECT_ROOT).glob("**/*.pdf"))
    if pdfs:
        return str(pdfs[0])
    
    return path

def run_vlm_workflow_test(pdf_path):
    """
    执行完整的 VLM 解析流程测试
    """
    if not os.path.exists(pdf_path):
        logger.error(f"错误: 未找到测试 PDF 文件: {pdf_path}")
        print(f"\n[FAILURE] File not found: {pdf_path}")
        return

    logger.info(f"开始测试文件: {pdf_path}")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    with tempfile.TemporaryDirectory() as temp_dir:
        file_name = os.path.splitext(os.path.basename(pdf_path))[0]
        # 准备环境目录 (output/images, output/md)
        local_image_dir, local_md_dir = prepare_env(temp_dir, file_name, "auto")
        
        # 1. 初始化拦截器 (开启图片描述生成)
        # 注意: 需要确保环境变量 MM_VLM_API_KEY 等已配置，否则会使用默认或跳过描述生成
        image_writer = MyImageInterceptor(local_image_dir, enable_caption=True)
        
        server_url = os.getenv("VLLM_SERVER_URL", "http://vllm:8000/v1")
        
        # 设置模拟的任务参数环境变量 (参考 vlm_mode.py 和 docker-compose.yml)
        # 强制使用离线模式和国内模型源，防止尝试连接 huggingface.co
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['MINERU_MODEL_SOURCE'] = os.getenv('MINERU_MODEL_SOURCE', 'modelscope')
        os.environ['HF_ENDPOINT'] = os.getenv('HF_ENDPOINT', 'https://hf-mirror.com')
        
        os.environ['MINERU_VLM_FORMULA_ENABLE'] = 'true'
        os.environ['MINERU_VLM_TABLE_ENABLE'] = 'true'
        os.environ['MINERU_VLM_OCR_LANG'] = 'zh-CN''ch'
        
        logger.info("正在调用 doc_analyze 进行布局分析和 OCR...")
        # 2. 调用 doc_analyze
        middle_json, infer_result, _ = doc_analyze(
            pdf_bytes,
            image_writer=image_writer,
            backend="http-client",
            server_url=server_url,
            language="ch",
            inline_formula_enable=True,
        )
        
        # 3. 生成原始 Markdown 内容
        pdf_info = middle_json["pdf_info"]
        remote_image_path = "test_task_id/images"
        md_str = vlm_union_make(pdf_info, MakeMode.MM_MD, remote_image_path)
        
        # 4. 插入描述信息 (核心逻辑同步自 vlm_mode.py)
        logger.info(f"开始处理描述信息。共发现描述: {len(image_writer.image_descriptions)} 个")
        
        caption_inserted_count = 0
        for img_path, desc in image_writer.image_descriptions.items():
            img_filename = os.path.basename(img_path)
            logger.info(f"正在为图片插入描述: {img_filename}")
            
            # 使用正则匹配 Markdown 图片语法 ![](...img_filename)
            pattern = rf"!\[.*?\]\(.*{re.escape(img_filename)}\)"
            
            if re.search(pattern, md_str):
                def replace_func(match):
                    return f"{match.group(0)}\n\n> 图片说明: {desc}"
                md_str = re.sub(pattern, replace_func, md_str)
                caption_inserted_count += 1
                logger.info(f"成功为 {img_filename} 插入描述")
            else:
                logger.warning(f"在 Markdown 中未找到图片 {img_filename} 的引用，无法插入描述")
        
        # 5. 验证结果
        if len(image_writer.image_descriptions) > 0:
            logger.info(f"验证: 预期插入 {len(image_writer.image_descriptions)} 个描述，实际插入 {caption_inserted_count} 个")
            if caption_inserted_count == 0:
                raise AssertionError("PDF 中包含图片描述，但未能在 Markdown 中成功匹配并插入")
            if "图片说明:" not in md_str:
                raise AssertionError("生成的 Markdown 中缺失 '图片说明:' 标识")
        else:
            logger.warning("该 PDF 可能不包含图片或未触发图片描述生成，请检查 PDF 内容或 VLM 配置。")

        # 6. 保存结果供人工校验
        final_md_path = os.path.join(temp_dir, f"{file_name}_final.md")
        with open(final_md_path, "w", encoding="utf-8") as f:
            f.write(md_str)
        
        logger.info(f"测试完成。结果已保存至: {final_md_path}")
        # 如果是在 pytest 环境下运行，可以使用 -s 参数查看此输出
        print(f"\n[SUCCESS] Final Markdown saved to: {final_md_path}")

if __name__ == "__main__":
    # 从命令行参数获取路径，或者使用默认逻辑获取
    input_arg = sys.argv[1] if len(sys.argv) > 1 else None
    target_pdf = get_test_pdf_path(input_arg)
    
    try:
        run_vlm_workflow_test(target_pdf)
    except Exception as e:
        logger.exception(f"测试运行过程中发生异常: {e}")
        sys.exit(1)