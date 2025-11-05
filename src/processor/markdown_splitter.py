from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
import re
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
import nltk
from nltk.tokenize import sent_tokenize
import os
import threading
from loguru import logger
from .named_entity_recognition import append_entities_to_header  # 引入自动实体提取函数


DEVICE_MODE = os.getenv("DEFAULT_CUDA_DEVICE", "0") # 选择CUDA设备
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
class SingletonSentenceTransformer:
    """
    使用单例模式确保全程只创建一个 SentenceTransformer 实例。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, model_id='BAAI/bge-small-zh-v1.5', mirror=True, device=DEVICE_MODE):
        if cls._instance is None:
            with cls._lock:
                print(f"正在通过{os.getenv('HF_ENDPOINT')}加载模型：{model_id}（mirror={mirror}）,device={device}")
                cls._instance = SentenceTransformer(model_id, device=f'cuda:{device}')
                print("模型加载完成。")
        return cls._instance


def get_bge_sentence_transformer_singleton(model_id='BAAI/bge-small-zh-v1.5', mirror=True, device=DEVICE_MODE):
    """
    获取全局唯一的 SentenceTransformer 实例。
    """
    return SingletonSentenceTransformer(model_id=model_id, mirror=mirror, device=device)

def split_sentences_chinese(text):
    """
    使用正则表达式按中文标点分句，同时保留句尾标点
    """
    sentences = re.split(r'(?<=[。！？])', text)
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


def semantic_chunking_with_auto_clusters(text, max_chunk_size=500, model_id="BAAI/bge-small-zh-v1.5")->list[str]:
    """
    自动选择最佳簇数的语义切分
    """
    # Step 1: 分句
    sentences = split_mixed_sentences(text)
    if len(sentences) < 2:
        return [text.strip()]

    # Step 2: 向量化
    model = get_bge_sentence_transformer_singleton(model_id)
    embeddings = model.encode(sentences)

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

def process_markdown(md_text: str, max_length: int = 500) -> str:
    """
    使用 markdown-it-py 处理markdown文本，根据标题结构和内容长度进行分割。
    表格作为不可分割的元素，会直接复制到结果中。
    
    :param md_text: 输入的markdown文本
    :param max_length: 每段最大长度
    :return: 处理后的markdown文本
    """

    md = MarkdownIt("commonmark").enable('table')
    md.use(dollarmath_plugin,allow_space=True,allow_digits=True)
    tokens = md.parse(md_text)
    
    # 预先计算原始文本的行数组，避免在循环中重复计算
    # 这里的行数组是为了在后续的段落合并中，能够准确地定位到原始文本的位置
    original_lines = md_text.split('\n')
    
    # 整篇文章的分段放在这里
    result = []
    # 当前正在处理的段落内容
    current_content = []
    # 当前的各级标题
    title_stack = [""] * 6  # h1-h6

    def get_title_path():
        """
        获取当前标题路径（用于生成聚合标题）
        """
        return '|'.join([t for t in title_stack if t])

    def get_current_level():
        """
        获取当前标题层级（找到最深级的非空标题）
        """
        for i in range(5, -1, -1):
            if title_stack[i]:
                return i + 1
        return 1  # 默认最小一级

    def flush_content(special_element=None):
        """
        检查是否还有待处理内容
        如果有内容，则把这一段放到result中
        形成一个标题+内容的段落
        """
        if not current_content:
            return
        # 
        content = '\n'.join(current_content).strip()
        if not content:
            current_content.clear()
            return

        level = get_current_level()
        title_path = get_title_path()
        # 如果当前段落为表格，直接复制
        if special_element:
            header = f"{'#' * level} {title_path}|{special_element}" if title_path else f"{'#' * level} {special_element}"
            result.extend([header, content, "-" * 10])
        else:
            # 处理普通的文本段落

            if len(content) > max_length:
                # 使用段落切分法
                # chunks = split_paragraphs_with_overlap(content, max_length)
                # 使用句子语义近似程度切分
                chunks = semantic_chunking_with_auto_clusters(content, max_chunk_size=max_length)
                for i, chunk in enumerate(chunks, 1):
                    header = f"{'#' * level} {title_path}|Part {i}" if title_path else f"{'#' * level} Part {i}"
                    header = append_entities_to_header(header, chunk)
                    result.extend([header, chunk, "-" * 10])
            else:
                header = f"{'#' * level} {title_path}" if title_path else ""
                header = append_entities_to_header(header, content)
                if header:
                    result.append(header)
                    result.append("")  # 添加空行分隔标题和内容
                result.extend([content, "-" * 10])
        current_content.clear()

    i = 0
    while i < len(tokens):
        token = tokens[i]
        # 标题处理
        if token.type == "heading_open":
            flush_content()# 因为这是一个新的标题，所以要先把此前的内容放到result中
            level = int(token.tag[1]) # 是标题的HTML标签（如 h1 、 h2 ），通过取标签的第二个字符（数字部分）转换为整数，得到标题层级。
            inline_token = tokens[i + 1] # 获取标题的内容
            if inline_token.type == "inline": # 如果是inline类型，则提取其中的内容（标题的内容）
                title_stack[level - 1] = inline_token.content.strip() # 把标题内容放在标题栈中
                # 清空比当前标题更深的标题（可能是在上一个章节遗留下来的）
                for j in range(level, 6):
                    title_stack[j] = ""
            i += 3  # skip heading_open, inline, heading_close，proceed to next block
            continue

        # 表格处理（整个复制）
        elif token.type == "table_open":
            flush_content()
            table_start = token.map[0] if token.map else 0
            
            # 找到表格结束token
            table_end_token = None
            j = i + 1
            while j < len(tokens) and tokens[j].type != "table_close":
                j += 1
            
            if j < len(tokens):
                table_end_token = tokens[j]
                # 如果table_close没有map信息，寻找下一个有map信息的token
                if table_end_token.map and table_end_token.map[1]:
                    table_end = table_end_token.map[1]
                else:
                    # 寻找table_close之后第一个有map信息的token
                    table_end = None
                    for k in range(j + 1, len(tokens)):
                        if tokens[k].map and tokens[k].map[0] is not None:
                            table_end = tokens[k].map[0]  # 使用下一个元素的开始位置
                            break
                    # 启发式扫描：直到遇到非表格行；若未遇到，则表格到文末
                    if table_end is None:
                        for line_idx in range(table_start, len(original_lines)):
                            line = original_lines[line_idx].strip()
                            if not line or not (line.startswith('|') or '|' in line):
                                table_end = line_idx
                                break
                        if table_end is None:
                            table_end = len(original_lines)
            else:
                # 没找到table_close，使用启发式方法：直到遇到非表格行；若未遇到，则到文末
                table_end = None
                for line_idx in range(table_start, len(original_lines)):
                    line = original_lines[line_idx].strip()
                    if not line or not (line.startswith('|') or '|' in line):
                        table_end = line_idx
                        break
                if table_end is None:
                    table_end = len(original_lines)
            
            # 提取表格内容（包含所有行直至 table_end）
            table_content = '\n'.join(original_lines[table_start:table_end])
            
            current_content.append(table_content)
            flush_content(special_element='Table')
            i = j + 1
            continue

        # 段落内容
        elif token.type == "paragraph_open":
            inline_token = tokens[i + 1]
            if inline_token.type == "inline":
                current_content.append(inline_token.content.strip())
            i += 3  # paragraph_open, inline, paragraph_close
            continue

        # 代码块
        elif token.type == "fence":
            current_content.append(f"```\n{token.content}\n```")
            i += 1
            continue
            
        # 有序列表处理
        elif token.type == "ordered_list_open":
            flush_content()
            list_content = []
            j = i + 1
            list_item_counter = 1
            
            while j < len(tokens) and tokens[j].type != "ordered_list_close":
                if tokens[j].type == "list_item_open":
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != "list_item_close":
                        if tokens[k].type == "paragraph_open" and k + 1 < len(tokens) and tokens[k + 1].type == "inline":
                            list_content.append(f"{list_item_counter}. {tokens[k + 1].content.strip()}")
                            list_item_counter += 1
                        k += 1
                j += 1
            
            if list_content:
                current_content.extend(list_content)
                flush_content(special_element=token.type)  # 立即处理列表内容
            i = j + 1
            continue
            
        # 无序列表处理
        elif token.type == "bullet_list_open":
            flush_content()
            list_content = []
            j = i + 1
            
            while j < len(tokens) and tokens[j].type != "bullet_list_close":
                if tokens[j].type == "list_item_open":
                    # 找到对应的inline token
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != "list_item_close":
                        if tokens[k].type == "paragraph_open" and k + 1 < len(tokens) and tokens[k + 1].type == "inline":
                            list_content.append(f"- {tokens[k + 1].content.strip()}")
                        k += 1
                j += 1
            
            if list_content:
                current_content.extend(list_content)
                flush_content(special_element=token.type)  # 立即处理列表内容
            i = j + 1
            continue
            
        # HTML块处理
        elif token.type == "html_block":
            current_content.append(token.content.strip())
            flush_content(special_element=token.type)  # 立即处理HTML块
            i += 1
            continue
            
        # 跳过列表相关的关闭标签（已在上面处理）
        elif token.type in ["list_item_close", "ordered_list_close", "bullet_list_close", "list_item_open"]:
            i += 1
            continue
            
        # 数学公式
        elif token.type == "math_block":
            flush_content()
            print(f'数学公式:{token.content}')
            current_content.append(f"$$ {token.content} $$")
            flush_content(special_element='Math Block')
            i += 1
            continue
        # 其他内容
        else:
            logger.warning(f"无法处理的token类型: {token.type}, 内容: {getattr(token, 'content', 'N/A')}")  # 添加调试信息
            i += 1

    # 循环结束后，确保把最后一个段落刷入结果（无标题场景）
    flush_content()
    if result and result[-1] == "-" * 10:
        result.pop()

    return '\n'.join(result)


# region
# 测试代码
# if __name__ == "__main__":
#     # from .converters.doc_to_markdown import doc_to_markdown 
#     # file = '/Users/zhoushujian/Downloads/运维.docx'
#     # md_text = doc_to_markdown(file)
#     # with open("original_运维.md", 'w', encoding='utf-8') as f:
#     #     f.write(md_text)
#     with open("test.md", 'r', encoding='utf-8') as f:
#         md_text = f.read()
#     processed_md = process_markdown(md_text, max_length=500) 
#     # import subprocess
#     out_file = "processed_运维.md"
#     with open(out_file, 'w', encoding='utf-8') as f:
#         f.write(processed_md)    
#     print(f'处理后的markdown文件已保存到{out_file},现在来看看效果')
#     # subprocess.run(['open',out_file])
# # endregion
