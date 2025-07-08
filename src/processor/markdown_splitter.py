import re
from textwrap import wrap

def process_markdown(md_text: str, max_length: int = 300) -> str:

    """
    处理markdown文本，根据标题结构和内容长度进行分割。
    表格作为不可分割的元素，会直接复制到结果中。
    
    :param md_text: 输入的markdown文本（字符串格式）
    :param max_length: 每个段落的最大长度，默认为300
    :return: 处理后的markdown文本
    """

    # 初始化标题栈和结果列表
    title_stack = [""] * 6  # h1-h6
    result = []
    current_content = []
    
    # 预编译正则表达式
    header_pattern = re.compile(r'^(#{1,6})\s*(.*?)\s*$', re.MULTILINE)
    table_pattern = re.compile(
        r'^(\|.+\|\n)(?:\|[\-:\|]+\n)((?:\|.+\|\n?)+)',
        re.MULTILINE
    )
    
    def get_clean_title_path():
        """获取不带#的标题路径"""
        return '|'.join([t for t in title_stack if t])
    
    def get_current_level():
        """获取当前最低标题级别"""
        for i in range(5, -1, -1):
            if title_stack[i]:
                return i + 1  # 1-based
        return 0
    
    def flush_content(is_table=False):
        """处理当前累积的内容"""
        if not current_content:
            return
            
        content = '\n'.join(current_content)
        if not content.strip():
            current_content.clear()
            return
            
        title_path = get_clean_title_path()
        level = get_current_level()
        
        if is_table:
            # 表格特殊处理（不分割）
            header = f"{'#'*level} {title_path}|Table" if title_path else "Table"
            result.extend([header, content, "-" * 10])
        else:
            # 普通文本处理
            if len(content) > max_length:
                chunks = wrap(content, width=max_length)
                for i, chunk in enumerate(chunks, 1):
                    header = f"{'#'*level} {title_path}|Part {i}" if title_path else f"Part {i}"
                    result.extend([header, chunk, "-" * 10])
            else:
                header = f"{'#'*level} {title_path}" if title_path else ""
                if header:
                    result.append(header)
                result.extend([content, "-" * 10])
        
        current_content.clear()
    
    # 先提取表格
    tables = []
    def table_replacer(match):
        tables.append((match.start(), match.end(), match.group(0)))
        return f"\0TABLE{len(tables)-1}\0"
    
    md_text = table_pattern.sub(table_replacer, md_text)
    
    # 处理其他内容
    lines = md_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 处理表格占位符
        if "\0TABLE" in line:
            table_id = int(re.search(r'\0TABLE(\d+)\0', line).group(1))
            _, _, table_content = tables[table_id]
            current_content.append(table_content)
            flush_content(is_table=True)
            i += 1
            continue
        
        # 处理标题
        header_match = header_pattern.match(line)
        if header_match:
            flush_content()
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            title_stack[level-1] = title
            # 清空下级标题
            for j in range(level, 6):
                title_stack[j] = ""
            i += 1
            continue
        
        # 处理空行
        if not line.strip():
            flush_content()
            i += 1
            continue
        
        # 普通内容行
        current_content.append(line)
        i += 1
    
    flush_content()
    
    # 移除最后多余的分隔符
    if result and result[-1] == "-" * 10:
        result.pop()
    
    return '\n'.join(result)
