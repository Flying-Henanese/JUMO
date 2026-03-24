import re
from .semantic_splitter import semantic_chunking_with_auto_clusters
from processor.nlp_inference.factory import InferenceFactory

def infer_heading_level(title: str) -> int:
    r"""
    根据标题文本推断其层级级别（1-6级）。

    参数:
        title (str): 标题文本内容

    返回:
        int: 标题层级（1-6），默认返回1级

    推断逻辑:
        1. 数字编号格式（优先处理）:
           - 匹配模式: "1", "1.1", "1.2.3", "1)", "1、" 等
           - 层级规则: 根据小数点的数量确定层级
             * "1" 或 "1)" 或 "1、" → 1级
             * "1.1" → 2级
             * "1.2.3" → 3级
             * 以此类推，最多6级
           - 正则表达式: r'^\s*(\d+(?:\.\d+)*)[.)、]?\s*'
             * ^\s* - 开头的空白字符
             * (\d+(?:\.\d+)*) - 数字部分，支持嵌套小数点
             * [.)、]? - 可选的结束符号（右括号、句点、中文顿号）
             * \s* - 结尾的空白字符

        2. 中文数字编号格式:
           - 匹配模式: "一、", "二、", "三、" 等
           - 层级规则: 统一作为1级标题处理
           - 正则表达式: r'^\s*[一二三四五六七八九十百千]+[、.]\s*'

        3. 默认情况:
           - 如果没有匹配到任何编号格式，默认返回1级
    """
    m = re.match(r'^\s*(\d+(?:\.\d+)*)[.)、]?\s*', title)
    if m:
        return max(1, min(len(m.group(1).split('.')), 6))
    m_zh = re.match(r'^\s*[一二三四五六七八九十百千]+[、.]\s*', title)
    if m_zh:
        return 1
    return 1

def get_title_path(stack: list[str]) -> str:
    """
    根据标题栈生成标题路径，用"|"分隔。

    参数:
        stack (list[str]): 标题层级栈，每个元素为一个标题文本

    返回:
        str: 标题路径，例如 "1|2|3" 表示一级二级三级标题
    """
    return '|'.join([t for t in stack if t])

def extract_table_block(tokens, i, original_lines):
    """
    从token流和原始文本中提取完整的表格块。

    该函数用于从markdown-it-py解析的token流中提取表格内容，并结合原始文本行
    来准确定位表格的起始和结束位置。这是处理表格的关键步骤，确保表格内容
    能够被完整提取而不被切分。

    参数:
        tokens: markdown-it-py解析生成的token列表
        i: 当前token的索引（应该是table_open类型的token）
        original_lines: 原始Markdown文本的行列表，用于提取实际表格内容

    返回:
        tuple: (j, table_content)
            - j: table_close token的索引，用于主循环继续处理
            - table_content: 提取的完整表格内容字符串（Markdown格式）
    """
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

def split_text_by_length_and_newline(text: str, max_length: int) -> list[str]:
    """
    层次化文本切分策略：先按段落分，再按行分，最后按语义分。
    现在的切分阈值 max_length 是以 Token 数量为准。

    该函数采用三层切分策略，确保文本的语义完整性：
    1. 第一层：按空行切分成段落（保持段落完整性）
    2. 第二层：对超长段落按行切分（保持行完整性）
    3. 第三层：对超长行进行语义切分（保持句子语义）

    参数:
        text (str): 待切分的文本内容
        max_length (int): 每个chunk的最大 Token 数量

    返回:
        list[str]: 切分后的文本块列表
    """
    chunks = []
    client = InferenceFactory.get_embedding_client()
    
    # 第一层：按空行切分成段落
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        # 获取段落的 token 数量
        paragraph_token_count = client.get_token_count(paragraph)

        # 如果段落本身不超过max_length Token，直接作为一个chunk
        if paragraph_token_count <= max_length:
            chunks.append(paragraph)
            continue
        
        # 第二层：对超长段落按行切分
        lines = paragraph.split('\n')
        current_chunk_lines = []
        current_chunk_tokens = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_token_count = client.get_token_count(line)
            # 添加一行所需的 token 开销（通常 \n 是 1 token）
            added_tokens = line_token_count + (1 if current_chunk_lines else 0)
            
            # 第三层：对超长行进行语义切分
            if line_token_count > max_length:
                # 先把当前积累的内容flush掉
                if current_chunk_lines:
                    chunks.append('\n'.join(current_chunk_lines))
                    current_chunk_lines = []
                    current_chunk_tokens = 0
                
                # 对超长行进行语义切分
                sub_chunks = semantic_chunking_with_auto_clusters(line, max_chunk_size=max_length)
                chunks.extend(sub_chunks)
            
            # 如果加上当前行会超过max_length，先flush
            elif current_chunk_tokens + added_tokens > max_length:
                chunks.append('\n'.join(current_chunk_lines))
                current_chunk_lines = [line]
                current_chunk_tokens = line_token_count
            
            # 否则加入当前块
            else:
                current_chunk_lines.append(line)
                current_chunk_tokens += added_tokens
        
        # 处理段落最后剩余的内容
        if current_chunk_lines:
            chunks.append('\n'.join(current_chunk_lines))
    
    return chunks