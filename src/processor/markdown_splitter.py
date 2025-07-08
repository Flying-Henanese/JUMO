import re
from textwrap import wrap

def process_markdown(md_text: str, max_length: int = 200) -> str:
    """
    处理Markdown文本，将其按照指定长度进行分割。
    
    :param md_text: 输入的Markdown文本
    :param max_length: 每个段落的最大长度，默认为300
    :return: 处理后的Markdown文本
    """
    # 初始化标题栈和结果列表
    title_stack = [""] * 6  # 支持h1-h6
    result = []
    current_paragraph = []
    
    # 预编译正则表达式
    header_pattern = re.compile(r'^(#{1,6})\s*(.*?)\s*$', re.MULTILINE)
    empty_line_pattern = re.compile(r'^\s*$', re.MULTILINE)
    
    def get_clean_title_path():
        """获取干净的标题路径（不带#标记）"""
        return '|'.join([t for t in title_stack if t])
    
    def get_current_header():
        """获取当前有效的标题级别和内容"""
        for i in range(5, -1, -1):
            if title_stack[i]:
                return (i+1, title_stack[i])  # (level, title)
        return (0, "")
    
    def flush_paragraph():
        if not current_paragraph:
            return
            
        content = ' '.join(line.strip() for line in current_paragraph if line.strip())
        if not content:
            current_paragraph.clear()
            return
            
        title_path = get_clean_title_path()
        current_level, current_title = get_current_header()
        
        if len(content) > max_length:
            chunks = wrap(content, width=max_length)
            for i, chunk in enumerate(chunks, 1):
                if title_path:
                    header = f"{'#'*current_level} {title_path}|Part {i}"
                else:
                    header = f"Part {i}"
                result.append(header)
                result.append(chunk)
                result.append("-" * 10)
        else:
            if title_path:
                header = f"{'#'*current_level} {title_path}"
                result.append(header)
            result.append(content)
            result.append("-" * 10)
        
        current_paragraph.clear()
    
    # 按行处理文本
    lines = md_text.split('\n')
    for line in lines:
        header_match = header_pattern.match(line)
        if header_match:
            flush_paragraph()
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            title_stack[level-1] = title
            # 清空下级标题
            for i in range(level, 6):
                title_stack[i] = ""
            continue
        
        if empty_line_pattern.match(line):
            flush_paragraph()
            continue
        
        current_paragraph.append(line)
    
    flush_paragraph()
    
    # 移除最后多余的分隔符
    if result and result[-1] == "-" * 10:
        result.pop()
    
    return '\n'.join(result)
