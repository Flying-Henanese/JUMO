import sys
from pathlib import Path
import pytest
import os 
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 将 src 加入 sys.path，便于导入 processor 包
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from processor.markdown_splitter import process_markdown
from processor.named_entity_recognition import extract_entities_auto


def test_markdown_ner_integration():
    # 读取测试文件
    test_file = ROOT / "test.md"
    with open(test_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 执行切分和实体识别
    processed_md = process_markdown(content)
    # entities = extract_entities_auto(processed_md)
    # 把结果写入到一个文件中 
    with open(ROOT / "test_processed.md", "w", encoding="utf-8") as f:
        f.write(processed_md)
    print("看结果")