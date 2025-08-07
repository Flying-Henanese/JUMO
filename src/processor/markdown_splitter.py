from markdown_it import MarkdownIt


def split_text_with_overlap(text: str, max_length: int = 800, overlap: int = 50) -> list[str]:
    """
    将文本按 max_length 切分，每段之间有 overlap 个字符的重叠部分。
    """
    assert max_length > overlap, "max_length 必须大于 overlap"
    
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_length, len(text))
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start += max_length - overlap
    return chunks

def split_paragraphs_with_overlap(text: str, max_length: int = 800, overlap: int = 50) -> list[str]:
    """
    根据段落优先的方式切分文本，长段落再用滑窗+重叠字符切分。
    
    :param text: 原始 Markdown 文本
    :param max_length: 每段最大长度
    :param overlap: 长段落之间的重叠字符数
    :return: 分段结果列表
    """
    assert max_length > overlap, "max_length 必须大于 overlap"

    paragraphs = [p.strip() for p in text.strip().split('\n\n') if p.strip()]
    result = []

    for para in paragraphs:
        if len(para) <= max_length:
            result.append(para)
        else:
            start = 0
            while start < len(para):
                end = min(start + max_length, len(para))
                chunk = para[start:end].strip()
                result.append(chunk)
                start += max_length - overlap

    return result

def process_markdown(md_text: str, max_length: int = 800) -> str:
    """
    使用 markdown-it-py 处理markdown文本，根据标题结构和内容长度进行分割。
    表格作为不可分割的元素，会直接复制到结果中。
    
    :param md_text: 输入的markdown文本
    :param max_length: 每段最大长度
    :return: 处理后的markdown文本
    """

    md = MarkdownIt("commonmark").enable('table')
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

    def flush_content(is_table=False):
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
        if is_table:
            header = f"{'#' * level} {title_path}|Table" if title_path else "Table"
            result.extend([header, content, "-" * 10])
        else:
            # 处理普通的文本段落
            if len(content) > max_length:
                # 如果段落长度超过了最大长度，则进行切分
                chunks = split_paragraphs_with_overlap(content, max_length)
                for i, chunk in enumerate(chunks, 1):
                    header = f"{'#' * level} {title_path}|Part {i}" if title_path else f"Part {i}"
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

        # 其他内容
        else:
            i += 1

    flush_content()

    if result and result[-1] == "-" * 10:
        result.pop()

    return '\n'.join(result)
