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
                if mirror:
                    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
                print(f"正在加载模型：{model_id}（mirror={mirror}）…")
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

# region
def split_paragraphs_with_overlap(text: str, max_length: int = 500, overlap: int = 50) -> list[str]:
    """
    根据段落优先的方式切分文本：
    1. 先将短段落聚合，保证每段尽量接近 max_length。
    2. 对过长段落使用滑窗+重叠字符切分。
    
    :param text: 原始 Markdown 文本
    :param max_length: 每段最大长度
    :param overlap: 长段落之间的重叠字符数
    :return: 分段结果列表
    """
    assert max_length > overlap, "max_length 必须大于 overlap"

    # 初步拆分段落并去掉空段落
    paragraphs = [p.strip() for p in text.strip().split('\n\n') if p.strip()]
    
    # 聚合短段落
    aggregated_paragraphs = []
    current_chunk = ""
    for para in paragraphs:
        # 检查当前段落加上现在正在处理的段落是否超过 max_length
        # 如果不超过的话可以进行整合
        if len(current_chunk) + len(para) + 2 <= max_length:  # +2 预留换行符
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        # 如果超过的话，之前的current_chunk自己成为一段
        # 然后当前段落成为新的current_chunk
        else:
            if current_chunk:
                aggregated_paragraphs.append(current_chunk)
            current_chunk = para
    # 最后有剩余的段落，没有后续的段落和他作伴了
    # 所以直接加入结果
    if current_chunk:
        aggregated_paragraphs.append(current_chunk)

    # 对过长段落使用滑窗切分
    result = []
    for para in aggregated_paragraphs:
        if len(para) <= max_length:
            result.append(para)
        else:
            result.extend(semantic_chunking_with_auto_clusters(para, max_length))

    return result
# endregion

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

def process_markdown(md_text: str, max_length: int = 800) -> str:
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
    result = []
    current_content = []
    title_stack = [""] * 6  # h1-h6

    def get_title_path():
        """
        获取当前标题路径
        """
        return '|'.join([t for t in title_stack if t])

    def get_current_level():
        """
        获取当前标题层级
        """
        for i in range(5, -1, -1):
            if title_stack[i]:
                return i + 1
        return 1  # 默认最小一级

    def flush_content(special_element=None):
        """
        检查是否还有待处理内容
        """
        if not current_content:
            return
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
                    result.extend([header, chunk, "-" * 10])
            else:
                header = f"{'#' * level} {title_path}" if title_path else ""
                if header:
                    result.append(header)
                result.extend([content, "-" * 10])
        current_content.clear()

    i = 0
    while i < len(tokens):
        token = tokens[i]
        # 标题处理
        if token.type == "heading_open":
            flush_content()
            level = int(token.tag[1])
            inline_token = tokens[i + 1]
            if inline_token.type == "inline":
                title_stack[level - 1] = inline_token.content.strip()
                for j in range(level, 6):
                    title_stack[j] = ""
            i += 3  # skip heading_open, inline, heading_close
            continue

        # 表格处理（整个复制）
        elif token.type == "table_open":
            flush_content()
            table_lines = []
            while i < len(tokens) and tokens[i].type != "table_close":
                if tokens[i].type == "inline":
                    table_lines.append(tokens[i].content)
                i += 1
            i += 1  # skip table_close
            current_content.append('\n'.join(table_lines))
            flush_content(is_table=True)
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
            i += 1

    flush_content()

    if result and result[-1] == "-" * 10:
        result.pop()

    return '\n'.join(result)


# region
# 测试代码
if __name__ == "__main__":
    markdown_file = "test.md"
    with open(markdown_file, 'r', encoding='utf-8') as f:
        md_text = f.read()
    print("access the file")
    processed_md = process_markdown(md_text, max_length=500)
    print(processed_md) 
