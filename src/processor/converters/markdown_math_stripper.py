# 从 Markdown 中移除数学公式
import re

from typing import Dict, Any

def _clean_latex_content_string(content: str) -> str:
    """
    核心清洗逻辑：去除LaTeX命令和特殊符号，只保留字母数字和空白。
    """
    if not content or not content.strip():
        return content

    # A. 替换所有反斜杠命令 \word 为空格
    cleaned = re.sub(r'\\[a-zA-Z]+', ' ', content)
    
    # B. 移除剩余的特殊符号，只保留字母数字和空格
    # 使用 \w 匹配 [a-zA-Z0-9_] 以及 unicode 字符（如中文）
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
    
    # C. 去除下划线
    cleaned = cleaned.replace('_', ' ')
    
    # D. 规范化空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def strip_latex_from_markdown(markdown_text: str) -> str:
    """
    去除Markdown中的行内LaTeX公式特殊符号，只保留字母和数字及基本空白。
    
    稳健性增强：
    1. 优先保护代码块 (```...```) 和行内代码 (`...`)，防止代码中的 $ 被误判。
    2. 保护行间公式 ($...$)。
    3. 仅处理行内公式 ($...$)。
    
    Args:
        markdown_text: 原始Markdown文本
        
    Returns:
        清洗后的文本
    """
    if not markdown_text:
        return ""

    placeholders = []
    
    def create_placeholder(match):
        placeholders.append(match.group(0))
        return f"__PROTECTED_BLOCK_{len(placeholders)-1}__"

    # 1. 保护代码块 (```...```) - 非贪婪匹配
    # re.S (DOTALL) 让 . 匹配换行符
    text_safe = re.sub(r'(```[\s\S]*?```)', create_placeholder, markdown_text)
    
    # 2. 保护行内代码 (`...`) 
    # 注意：Markdown中行内代码不能跨行（通常），且可能有多个反引号
    text_safe = re.sub(r'(`+)(.*?)(\1)', create_placeholder, text_safe)

    # 3. 保护行间公式 ($...$)
    text_safe = re.sub(r'(\$\$[\s\S]*?\$\$)', create_placeholder, text_safe)
    
    # 4. 处理行内公式：匹配 $...$
    # 排除 \$ 转义的情况（虽然在这个简单版本中可能不用太纠结，但为了稳健最好处理）
    # 这里的正则假设 $ 内部没有未转义的 $
    inline_math_pattern = re.compile(r'\$((?:\\.|[^$])+?)\$')
    
    def clean_inline_latex(match):
        latex_content = match.group(1)
        # 调用提取出来的核心清洗逻辑
        cleaned_content = _clean_latex_content_string(latex_content)
        # 如果清洗后为空，可能只剩空格，这里我们返回原始内容的纯文本形式或者直接返回清洗结果
        # 但要注意，如果是 $...$，我们要去掉 $
        return cleaned_content

    text_cleaned = inline_math_pattern.sub(clean_inline_latex, text_safe)
    
    # 5. 还原所有保护块
    # 注意：需要按相反顺序还原吗？不需要，因为占位符是唯一的。
    # 但为了保险，我们按索引顺序还原。
    for i, content in enumerate(placeholders):
        text_cleaned = text_cleaned.replace(f"__PROTECTED_BLOCK_{i}__", content)
        
    return text_cleaned

def strip_latex_from_json_structure(middle_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    遍历middle.json结构，清洗inline_equation类型的span内容。
    直接在原字典上修改。
    
    Args:
        middle_json: 符合MinerU middle.json规范的字典
        
    Returns:
        修改后的middle_json
    """
    pdf_info = middle_json.get('pdf_info', [])
    if not pdf_info:
        return middle_json
        
    for page in pdf_info:
        for block in page.get('para_blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    # 仅处理行内公式
                    if span.get('type') == 'inline_equation':
                        original_content = span.get('content', '')
                        # 清洗内容
                        span['content'] = _clean_latex_content_string(original_content)
                        
    return middle_json
