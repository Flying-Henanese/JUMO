"""
Markdown 语义分割器与标题增强器
==============================================

本模块负责对 Markdown 内容进行后处理，使其适用于知识库索引（RAG 应用）。
它执行文本的语义切分，并重构层级标题，以确保每个文本块都能保留其上下文。

主要功能:
-------------
1.  **语义切分 (Semantic Chunking)**:
    -   使用 `SentenceTransformer`（例如 BAAI/bge-small-zh-v1.5）为句子生成嵌入向量。
    -   应用 `AgglomerativeClustering` 将语义相似的句子聚类成块。
    -   根据内容长度动态确定最佳聚类数量。

2.  **标题重构 (Header Reconstruction)**:
    -   使用 `markdown-it-py` 将 Markdown 解析为 token 流。
    -   在遍历文档时维护当前标题（H1-H6）的堆栈。
    -   将父标题的完整路径（例如 `# H1 > H2 > H3`）注入到每个文本块中。
    -   确保即使是微小的文本块也能携带其结构上下文，这对于向量检索至关重要。

3.  **特殊块处理 (Special Block Handling)**:
    -   检测并保留表格、列表、代码块和数学公式。
    -   将这些块视为原子单元，或在保留其标题的同时适当地对其进行分段。

用法:
------
主要入口点是 `process_markdown(md_text, max_length=500)`。
它输入原始 Markdown 文本并输出处理后的 Markdown 字符串，其中：
-   长段落被语义切分。
-   每个块之前都有其层级标题。
-   块之间用 `----------` 分隔。
"""
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
import re
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
import nltk
from nltk.tokenize import sent_tokenize
import threading
from loguru import logger
from utils.auto_device_selector import get_device
from processor.converters.table_to_markdown import html_table_to_key_value
from processor.nlp_inference.factory import InferenceFactory
from .named_entity_recognition import append_entities_to_header  # 引入自动实体提取函数


# 确保 punkt_tab 可用
# 首先检测是否已存在punkt_tab模型
# 如果加载失败，尝试下载
try:
    nltk.data.find('tokenizers/punkt_tab') # punkt_tab 是 NLTK 用于分句的模型
except LookupError:
    nltk.download('punkt_tab')
"""
不论是word,pdf还是图片，最终都会被转换成markdown格式
在这个模块中会把生成的中间markdown进行切分处理，使得其
可以在知识库应用中被合理地向量化
"""

def split_sentences_chinese(text):
    """
    使用正则表达式按中文标点分句，同时保留句尾标点
    """
    # 1. (?<=[。！？])(?![”’"]) : 匹配标点符号，且后面不是引号
    # 2. (?<=[。！？][”’"])    : 匹配标点符号后紧跟引号的组合
    pattern = r'(?<=[。！？])(?![”’"])|(?<=[。！？][”’"])'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]

def split_mixed_sentences(text: str) -> list[str]:
    """
    能同时处理中文和英文分句。
    英文段落使用 NLTK；中文段落使用 zh regex 或 fallback。
    """
    chunks = re.split(r'(\n+)', text)  # 粗略按行分隔，并保留换行符
    sentences = []

    for ch in chunks:
        if not ch.strip():
            continue
        # 英文段落判断：包含 [a-zA-Z] 且结束有 . ? ! 空格
        if re.search(r'[A-Za-z]', ch):
            parts = sent_tokenize(ch) # 使用 NLTK 分句
            sentences.extend([p.strip() for p in parts if p.strip()])
        # 中文段落判断：非英文段落就是中文段落
        else:
            # 优先用 zhon 精确匹配
            sents = split_sentences_chinese(ch) # 使用比较简单的自定义中文分句
            if sents:
                sentences.extend([s.strip() for s in sents if s.strip()])
            else:
                parts = re.split(r'(?<=[。！？])', ch)
                sentences.extend([p.strip() for p in parts if p.strip()])
    return sentences


def find_best_num_clusters(embeddings, min_clusters=2, max_clusters=10):
    """
    使用轮廓系数选择最佳簇数
    实际效果不是很好，先放这里，待后续研究
    """
    best_score = -1
    best_k = min_clusters

    for k in range(min_clusters, min(max_clusters, len(embeddings)) + 1):
        labels = AgglomerativeClustering(n_clusters=k).fit_predict(embeddings)
        if len(set(labels)) == 1:  # 全部在同一簇 → 跳过
            continue
        score = silhouette_score(embeddings, labels)
        if score > best_score:
            best_score = score
            best_k = k

    return best_k


def semantic_chunking_with_auto_clusters(text, max_chunk_size=500, model_id="BAAI/bge-small-zh-v1.5"):
    """
    自动选择最佳簇数的语义切分
    """
    # Step 1: 分句
    sentences = split_mixed_sentences(text)
    if len(sentences) < 2:
        return [text.strip()]

    # Step 2: 向量化
    client = InferenceFactory.get_embedding_client()
    embeddings = client.encode(sentences)

    # Step 3: 自动选择最佳簇数
    # 这里使用最简单无脑的方法, 簇数 = 句子数//最大段落长度+1
    best_k = max(len(sentences)//max_chunk_size,1)+1
    # Step 4: 聚类
    labels = AgglomerativeClustering(n_clusters=best_k).fit_predict(embeddings)

    # Step 5: 按聚类结果组合句子，并限制段落大小
    chunks = []
    current_chunk = ""
    current_label = labels[0]

    for sentence, label in zip(sentences, labels):
        if label != current_label or len(current_chunk) + len(sentence) > max_chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = sentence
            current_label = label
        else:
            current_chunk += sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks

def _infer_heading_level(title: str) -> int:
    m = re.match(r'^\s*(\d+(?:\.\d+)*)[.)、]?\s*', title)
    if m:
        return max(1, min(len(m.group(1).split('.')), 6))
    m_zh = re.match(r'^\s*[一二三四五六七八九十百千]+[、.]\s*', title)
    if m_zh:
        return 1
    return 1

def _get_title_path(stack: list[str]) -> str:
    return '|'.join([t for t in stack if t])

def split_text_by_length_and_newline(text: str, max_length: int) -> list[str]:
    """
    优先按换行符切分，如果单行超过max_length再进行语义切分。
    尽可能合并短行以填充max_length。
    """
    lines = text.split('\n')
    chunks = []
    current_chunk_lines = []
    current_chunk_len = 0
    
    for line in lines:
        line_len = len(line)
        
        # 计算如果加入当前行后的总长度（包含换行符）
        # 如果 current_chunk_lines 不为空，则需要加一个换行符，长度+1
        added_len = line_len + (1 if current_chunk_lines else 0)
        
        # 1. 如果单行本身就超过 max_length
        if line_len > max_length:
            # 先把当前积累的内容flush掉
            if current_chunk_lines:
                chunks.append('\n'.join(current_chunk_lines))
                current_chunk_lines = []
                current_chunk_len = 0
            
            # 对超长行进行语义切分
            sub_chunks = semantic_chunking_with_auto_clusters(line, max_chunk_size=max_length)
            chunks.extend(sub_chunks)
            
        # 2. 如果加上当前行会超过 max_length
        elif current_chunk_len + added_len > max_length:
            chunks.append('\n'.join(current_chunk_lines))
            current_chunk_lines = [line]
            current_chunk_len = line_len
            
        # 3. 否则加入当前块
        else:
            current_chunk_lines.append(line)
            current_chunk_len += added_len
            
    # 处理最后剩余的内容
    if current_chunk_lines:
        chunks.append('\n'.join(current_chunk_lines))
        
    return chunks


def _flush_content(result, current_content, title_stack, max_length, special_element=None, allow_split=False) -> None:
    if not current_content:
        return
    content = '\n'.join(current_content).strip()
    if not content:
        current_content.clear()
        return
    level = next((i + 1 for i in range(5, -1, -1) if title_stack[i]), 1)
    title_path = _get_title_path(title_stack)
    
    if special_element and not allow_split:
        header = f"{'#' * level} {title_path}|{special_element}" if title_path else f"{'#' * level} {special_element}"
        # header = append_entities_to_header(header, content)
        result.extend([header, content, '-' * 10])
    else:
        # 如果允许切分（无论是普通文本还是特殊的allow_split元素）
        if len(content) > max_length:
            chunks = semantic_chunking_with_auto_clusters(content, max_chunk_size=max_length)
            for idx, chunk in enumerate(chunks, 1):
                # 构建基础标题
                base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
                # 如果有special_element，加到中间
                if special_element:
                    header = f"{base_header}|{special_element}|Part {idx}"
                else:
                    header = f"{base_header}|Part {idx}"
                header = append_entities_to_header(header, chunk)
                result.extend([header, chunk, '-' * 10])
        else:
            base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
            if special_element:
                header = f"{base_header}|{special_element}"
            else:
                header = base_header
            
            header = append_entities_to_header(header, content)
            
            if header:
                result.append(header)
                result.append("")
            result.extend([content, '-' * 10])
    current_content.clear()


def _extract_table_block(tokens, i, original_lines):
    token = tokens[i]
    table_start = token.map[0] if token.map else 0
    j = i + 1
    while j < len(tokens) and tokens[j].type != 'table_close':
        j += 1
    if j < len(tokens):
        end_token = tokens[j]
        if end_token.map and end_token.map[1] is not None:
            table_end = end_token.map[1]
        else:
            table_end = None
            for k in range(j + 1, len(tokens)):
                if tokens[k].map and tokens[k].map[0] is not None:
                    table_end = tokens[k].map[0]
                    break
            if table_end is None:
                table_end = table_start + 1
                for line_idx in range(table_start, len(original_lines)):
                    line = original_lines[line_idx].strip()
                    if not line or not (line.startswith('|') or '|' in line):
                        table_end = line_idx
                        break
    else:
        table_end = table_start + 1
        for line_idx in range(table_start, len(original_lines)):
            line = original_lines[line_idx].strip()
            if not line or not (line.startswith('|') or '|' in line):
                table_end = line_idx
                break
    return j, '\n'.join(original_lines[table_start:table_end])


def process_markdown(md_text: str, max_length: int = 500) -> str:
    md = MarkdownIt('commonmark').enable('table')
    md.use(dollarmath_plugin, allow_space=True, allow_digits=True)
    tokens = md.parse(md_text)
    original_lines = md_text.split('\n')
    result = []
    current_content = []
    title_stack = [''] * 6

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == 'heading_open':
            _flush_content(result, current_content, title_stack, max_length)
            inline_token = tokens[i + 1]
            if inline_token.type == 'inline':
                full_title = inline_token.content.strip()
                level = _infer_heading_level(full_title)
                title_stack[level - 1] = full_title
                for j in range(level, 6):
                    title_stack[j] = ''
            i += 3
            continue
        elif token.type == 'table_open':
            _flush_content(result, current_content, title_stack, max_length)
            j, table_content = _extract_table_block(tokens, i, original_lines)
            current_content.append(table_content)
            _flush_content(result, current_content, title_stack, max_length, special_element='Table')
            i = j + 1 if j < len(tokens) else len(tokens)
            continue
        elif token.type == 'paragraph_open':
            inline_token = tokens[i + 1]
            if inline_token.type == 'inline':
                current_content.append(inline_token.content.strip())
            i += 3
            continue
        elif token.type == 'fence':
            current_content.append(f"```\n{token.content}\n```")
            i += 1
            continue
        elif token.type == 'ordered_list_open':
            _flush_content(result, current_content, title_stack, max_length)
            list_content = []
            j = i + 1
            list_item_counter = 1
            while j < len(tokens) and tokens[j].type != 'ordered_list_close':
                if tokens[j].type == 'list_item_open':
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != 'list_item_close':
                        if tokens[k].type == 'paragraph_open' and k + 1 < len(tokens) and tokens[k + 1].type == 'inline':
                            list_content.append(f"{list_item_counter}. {tokens[k + 1].content.strip()}")
                            list_item_counter += 1
                        k += 1
                j += 1
            if list_content:
                current_content.extend(list_content)
                _flush_content(result, current_content, title_stack, max_length, special_element=token.type)
            i = j + 1
            continue
        elif token.type == 'bullet_list_open':
            _flush_content(result, current_content, title_stack, max_length)
            list_content = []
            j = i + 1
            while j < len(tokens) and tokens[j].type != 'bullet_list_close':
                if tokens[j].type == 'list_item_open':
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != 'list_item_close':
                        if tokens[k].type == 'paragraph_open' and k + 1 < len(tokens) and tokens[k + 1].type == 'inline':
                            list_content.append(f"- {tokens[k + 1].content.strip()}")
                        k += 1
                j += 1
            if list_content:
                current_content.extend(list_content)
                _flush_content(result, current_content, title_stack, max_length, special_element=token.type)
            i = j + 1
            continue
        elif token.type == 'html_block':
            _flush_content(result, current_content, title_stack, max_length)
            content = token.content.strip()
            # 尝试检测是否为表格，并转换为KV格式
            # 如果转换成功，则将其标记为Table KV，并允许后续按行切分
            is_converted_table = False
            if '<table' in content.lower():
                try:
                    kv_list = html_table_to_key_value(content)
                    if kv_list:
                        # 将KV列表转换为Markdown列表格式的字符串
                        # 这样既能利用_flush_content的换行切分，又能保持视觉上的可读性
                        content = '\n'.join([f"- {item}" for item in kv_list])
                        is_converted_table = True
                except Exception as e:
                    logger.warning(f"HTML表格转KV失败: {e}")
            
            current_content.append(content)
            # 在这里把表格内容按行做切分，以防表格内容过长

            if is_converted_table:
                _flush_content(result, current_content, title_stack, max_length, special_element='Table KV', allow_split=True)
            else:
                _flush_content(result, current_content, title_stack, max_length, special_element=token.type)
            i += 1
            continue
        elif token.type in ['list_item_close', 'ordered_list_close', 'bullet_list_close', 'list_item_open']:
            i += 1
            continue
        elif token.type == 'math_block':
            _flush_content(result, current_content, title_stack, max_length)
            current_content.append(f"$ {token.content} $")
            _flush_content(result, current_content, title_stack, max_length, special_element='Math Block')
            i += 1
            continue
        else:
            logger.warning(f"无法处理的token类型: {token.type}, 内容: {getattr(token, 'content', 'N/A')}")
            i += 1

    # 循环结束后，将剩余的内容写入结果
    _flush_content(result, current_content, title_stack, max_length)

    if result and result[-1] == '-' * 10:
        result.pop()
    return '\n'.join(result)


# region
# 测试代码
if __name__ == "__main__":
    # 使用cuda:3设备进行推理
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    os.environ['DEFAULT_CUDA_DEVICE'] = 'cuda:0'
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
    with open("tests/test_resource/test.md", 'r', encoding='utf-8') as f:
        md_text = f.read()
    processed_md = process_markdown(md_text, max_length=500) 
    out_file = "tests/test_resource/processed_test.md"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(processed_md)    
    print(f'处理后的markdown文件已保存到{out_file},现在来看看效果')
# # endregion

