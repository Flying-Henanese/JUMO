import os
import json
import pytest
import tempfile
import sys
from pathlib import Path

# 设置项目根目录并加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from mineru.utils.enum_class import MakeMode
from mineru.backend.office.docx_analyze import office_docx_analyze
from mineru.backend.office.office_middle_json_mkcontent import union_make as office_union_make
from mineru.data.data_reader_writer import FileBasedDataWriter
from processor.converters.doc_to_markdown import doc_to_markdown

# 配置路径（相对于项目根目录）
INPUT_DIR = PROJECT_ROOT / "tests" / "test_resource" / "input"
OUTPUT_PATH_MINERU = PROJECT_ROOT / "tests" / "test_resource" / "output_mineru"
OUTPUT_PATH_DOCLING = PROJECT_ROOT / "tests" / "test_resource" / "output_docling"
IMAGE_DIR = PROJECT_ROOT / "tests" / "test_resource" / "images"

# 初始化图片写入器
image_writer = FileBasedDataWriter(str(IMAGE_DIR))

def get_word_files():
    """获取输入目录下的所有 docx 文件"""
    if not INPUT_DIR.exists():
        return []
    return [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.docx')]

@pytest.fixture(scope="session", autouse=True)
def setup_dirs():
    """测试前确保输出目录存在"""
    OUTPUT_PATH_MINERU.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH_DOCLING.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

@pytest.mark.parametrize("word_file", get_word_files())
def test_office_parsing_comparison(word_file):
    """对比 MinerU 和 Docling 对 Word 文档的解析效果"""
    file_path = INPUT_DIR / word_file
    file_name = file_path.stem
    
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # --- 1. MinerU 解析 ---
    try:
        middle_json, results = office_docx_analyze(file_bytes)
        pdf_info = middle_json["pdf_info"]
        md_str_mineru = office_union_make(pdf_info, MakeMode.MM_MD)
        
        clean_md_mineru = md_str_mineru.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
        output_file_mineru = OUTPUT_PATH_MINERU / f"{file_name}.md"
        with open(output_file_mineru, "w", encoding="utf-8") as f:
            f.write(clean_md_mineru)
        assert output_file_mineru.exists()
    except Exception as e:
        pytest.fail(f"MinerU 解析 {word_file} 失败: {e}")

    # --- 2. Docling 解析 ---
    try:
        suffix = ".docx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name

        try:
            md_content_docling = doc_to_markdown(
                input_data=temp_file_path,
                task_id=file_name,
                bucket=None,
                return_images=False
            )
            
            output_file_docling = OUTPUT_PATH_DOCLING / f"{file_name}.md"
            with open(output_file_docling, "w", encoding="utf-8") as f:
                f.write(md_content_docling)
            assert output_file_docling.exists()
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        pytest.fail(f"Docling 解析 {word_file} 失败: {e}")
