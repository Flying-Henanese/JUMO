"""
Markdown Semantic Splitter and Header Enhancer
==============================================

This module is responsible for post-processing Markdown content to make it suitable for
knowledge base indexing (RAG applications). It performs semantic chunking of text and
reconstructs hierarchical headers to ensure that every text chunk preserves its context.

Key Features:
-------------
1.  **Semantic Chunking**:
    -   Uses `SentenceTransformer` (e.g., BAAI/bge-small-zh-v1.5) to generate embeddings for sentences.
    -   Applies `AgglomerativeClustering` to group semantically similar sentences into chunks.
    -   Dynamically determines the optimal number of clusters based on content length.

2.  **Header Reconstruction**:
    -   Parses Markdown into a token stream using `markdown-it-py`.
    -   Maintains a stack of current headings (H1-H6) while traversing the document.
    -   Injects the full path of parent headings (e.g., `# H1 > H2 > H3`) into every text block.
    -   Ensures that even small chunks of text carry their structural context, which is crucial for vector retrieval.

3.  **Special Block Handling**:
    -   Detects and preserves tables, lists, code blocks, and math formulas.
    -   Treats these blocks as atomic units or segments them appropriately while keeping their headers.

Usage:
------
The main entry point is `process_markdown(md_text, max_length=500)`.
It inputs raw Markdown text and outputs a processed Markdown string where:
-   Long paragraphs are semantically split.
-   Every block is preceded by its hierarchical headers.
-   Blocks are separated by `----------`.
"""
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
import re
import os
from loguru import logger
from sentence_transformers import SentenceTransformer
from utils.auto_device_selector import get_device
from processor.converters.table_to_markdown import html_table_to_key_value
from .named_entity_recognition import append_entities_to_header  # 引入自动实体提取函数
from .enhancer.semantic_splitter import semantic_chunking_with_auto_clusters
from .enhancer.markdown_utils import infer_heading_level, get_title_path, extract_table_block, split_text_by_length_and_newline
from processor.nlp_inference.factory import InferenceFactory
import threading
"""
不论是word,pdf还是图片，最终都会被转换成markdown格式
在这个模块中会把生成的中间markdown进行切分处理，使得其
可以在知识库应用中被合理地向量化
"""
class SingletonSentenceTransformer:
    """
    使用单例模式确保全程只创建一个 SentenceTransformer 实例。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, model_id='BAAI/bge-small-zh-v1.5', mirror=True):
        if cls._instance is None:
            with cls._lock:
                target_device = get_device()
                logger.info(f"正在通过{os.getenv('HF_ENDPOINT')}加载模型：{model_id}（mirror={mirror}）, device={target_device}")
                cls._instance = SentenceTransformer(model_id, device=target_device)
                logger.info("模型加载完成。")
        return cls._instance


def get_bge_sentence_transformer_singleton(model_id='BAAI/bge-small-zh-v1.5', mirror=True):
    """
    获取全局唯一的 SentenceTransformer 实例。
    """
    return SingletonSentenceTransformer(model_id=model_id, mirror=mirror)

def _flush_content(
    result: list, 
    current_content: list, 
    title_stack: list, 
    max_length: int, 
    special_element: str = None, 
    allow_split: bool = False
    ) -> None:
    if not current_content:
        return
    # 合并当前所有的内容，使用换行符连接
    content = '\n'.join(current_content).strip()
    # 如果合并后的内容为空，直接返回
    if not content:
        current_content.clear()
        return

    # 从最深层级（H6）开始向上一层层查找，因为我们要找的是当前内容 最近 （最深）的那个父标题
    # 如果这一层有标题，那么就使用i+1作为当前内容的层级（因为要使用这个level确定#号的数量，所以+1）
    level = next((i + 1 for i in range(5, -1, -1) if title_stack[i]), 1)
    # 构建标题路径（使用这个函数在所有的元素之间添加|符号）
    title_path = get_title_path(title_stack)
    # 如果当前正在处理的是表格、列表、代码块、数学公式等特殊元素，
    # 那么就不允许切分（因为这些元素的内容是连续的，不应该被切分）
    if special_element and not allow_split:
        # 在这里直接构建标题，并把内容添加到结果列表中
        header = f"{'#' * level} {title_path}|{special_element}" if title_path else f"{'#' * level} {special_element}"
        result.extend([header, content, '-' * 10])
    else:
        # 如果允许切分（无论是普通文本还是特殊的allow_split元素）
        client = InferenceFactory.get_embedding_client()
        if client.get_token_count(content) > max_length:
            # 使用层次化切分策略：先按段落分，再按行分，最后按语义分
            chunks = split_text_by_length_and_newline(content, max_length)
            for idx, chunk in enumerate(chunks, 1):
                # 构建基础标题
                base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
                # 如果有special_element，加到中间
                if special_element:
                    header = f"{base_header}|{special_element}|Part {idx}"
                else:
                    header = f"{base_header}|Part {idx}"
                result.extend([header, chunk, '-' * 10])
        else:
            # 如果长度没有超过max_length，那么就直接添加到结果列表中
            # 以base_header作为标题,内容完整保留
            base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
            if special_element:
                header = f"{base_header}|{special_element}"
            else:
                header = base_header
            
            if header:
                result.append(header)
                result.append("")
            result.extend([content, '-' * 10])
    # 作为临时变量，current_content已经没有作用了，所以清空
    current_content.clear()




def _handle_image_caption(tokens, i, result, current_content, title_stack, max_length):
    """
    Attempts to handle image + caption logic.
    Returns (handled, new_i)
    """
    token = tokens[i]
    if token.type != 'paragraph_open':
        return False, i
        
    inline_token = tokens[i + 1]
    if inline_token.type != 'inline':
        return False, i
        
    content = inline_token.content.strip()
    image_pattern = r'^!\[.*?\]\(.*?\)\s*$'
    caption_pattern = r'^(?:Figure|图|Fig\.|表|Table)\s*[\d\w\.]+'

    # Logic 1: Image and caption in the same paragraph
    img_match = re.search(r'^(!\[.*?\]\(.*?\))', content)
    if img_match:
        rest = content[img_match.end():].strip()
        if rest and re.match(caption_pattern, rest, re.IGNORECASE):
            _flush_content(result, current_content, title_stack, max_length)
            current_content.append(content)
            caption_title = rest.split('\n')[0].strip()
            _flush_content(result, current_content, title_stack, max_length, special_element=caption_title)
            return True, i + 3

    # Logic 2: Image in current paragraph, caption in next paragraph
    if re.match(image_pattern, content):
        next_p_idx = i + 3
        if next_p_idx + 1 < len(tokens) and tokens[next_p_idx].type == 'paragraph_open':
            next_inline = tokens[next_p_idx + 1]
            if next_inline.type == 'inline':
                next_content = next_inline.content.strip()
                if re.match(caption_pattern, next_content, re.IGNORECASE):
                    _flush_content(result, current_content, title_stack, max_length)
                    current_content.append(content)
                    current_content.append(next_content)
                    _flush_content(result, current_content, title_stack, max_length, special_element=next_content)
                    return True, i + 6

    # Logic 3: Caption in current paragraph, image in previous paragraph (already in current_content)
    if current_content and re.match(caption_pattern, content, re.IGNORECASE):
        last_item = current_content[-1].strip()
        if re.match(image_pattern, last_item):
            image_tag = current_content.pop()
            _flush_content(result, current_content, title_stack, max_length)
            current_content.append(image_tag)
            current_content.append(content)
            _flush_content(result, current_content, title_stack, max_length, special_element=content)
            return True, i + 3

    return False, i

def process_markdown(md_text: str, max_length: int = 500) -> str:
    """
    使用MarkdownIt解析Markdown文本，将其切分成多个部分，每个部分的长度不超过max_length。
    单元为markdownit解析出来的token
    然后依次遍历每个token，根据token的类型进行处理
    1. 如果是标题，那么就把当前的内容（current_content）添加到结果列表中
    2. 如果是表格、列表、代码块、数学公式等特殊元素，那么就不允许切分（因为这些元素的内容是连续的，不应该被切分）
    3. 如果是普通的段落，那么就根据max_length切分内容，每个部分作为一个新的段落添加到结果列表中

    """
    # 初始化MarkdownIt解析器，开启表格解析功能
    md = MarkdownIt('commonmark').enable('table')
    # 开启数学公式解析插件，允许空格和数字
    md.use(dollarmath_plugin, allow_space=True, allow_digits=True)
    # 解析Markdown文本，得到token列表
    tokens: list = md.parse(md_text)
    # 将Markdown文本按行分割，得到原始行列表
    original_lines: list = md_text.split('\n')
    # 初始化结果列表，用于存储切分后的所有内容
    result: list = []
    # 初始化当前内容列表，用于存储当前处理的段落内容
    # 当前内容达到max_length时，会被添加到结果列表中
    current_content: list = []
    # 初始化标题栈，用于存储当前的标题层级
    title_stack: list = [''] * 6

    # 遍历每个token
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # 遇到了标题类型的token
        if token.type == 'heading_open':
            # 说明开始了一个新的章节，所以先把当前的内容添加到结果列表中,这里肯定是要开始新的段落的
            _flush_content(result, current_content, title_stack, max_length)
            # 这里其实就是标题记号后面实际的标题内容
            inline_token = tokens[i + 1]
            if inline_token.type == 'inline':
                full_title = inline_token.content.strip()
                # 得到标题级别
                level = infer_heading_level(full_title)
                # 然后把标题插入对应的标题栈中
                title_stack[level - 1] = full_title
                for j in range(level, 6):
                    title_stack[j] = ''
            i += 3
            continue
        # 遇到表格类型的token，需要特殊处理
        elif token.type == 'table_open':
            _flush_content(result, current_content, title_stack, max_length)
            j, table_content = extract_table_block(tokens, i, original_lines)
            current_content.append(table_content)
            _flush_content(result, current_content, title_stack, max_length, special_element='Table')
            i = j + 1 if j < len(tokens) else len(tokens)
            continue
        # 遇到段落类型的token
        elif token.type == 'paragraph_open':
            handled, new_i = _handle_image_caption(tokens, i, result, current_content, title_stack, max_length)
            if handled:
                i = new_i
                continue
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

