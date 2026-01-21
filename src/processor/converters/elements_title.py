"""
Markdown 表格标题增强
================================

本模块提供启发式方法，将 Markdown 文本中的表格标题与表格内容关联起来。
它解析 Markdown 结构以识别看起来像表格标题的标题（例如，“Table 1: ...”），
并在它们相邻时将其合并到相应的表格头中。

主要功能:
--------------
-   `enhance_table_titles`: 处理 Markdown 文本并合并标题的主函数。
"""
import re


def _detect_table_caption(text: str):
    """
    Detects if a string resembles a table caption.
    Matches patterns like "表 1", "Table 1", etc.
    """
    t = (text or "").strip()
    if not t:
        return None
    m = re.match(r'^\s*表\s*([一二三四五六七八九十百千\d]+)(?:\s*[:：.\-、]?\s*(.*))?$', t)
    if m:
        p2 = m.group(1)
        p3 = (m.group(2) or "").strip()
        return f"表 {p2}{(': ' + p3) if p3 else ''}".strip()
    m2 = re.match(r'^(?:table)\s*([0-9]+)(?:\s*[:.\-]?\s*(.*))?$', t, flags=re.I)
    if m2:
        p2 = m2.group(1)
        p3 = (m2.group(2) or "").strip()
        return f"Table {p2}{(': ' + p3) if p3 else ''}".strip()
    return None


def _is_heading(line: str):
    """Checks if a line is a Markdown heading (starts with #)."""
    return bool(re.match(r'^\s*#{1,6}\s+.+', line or ""))


def _get_heading_text(line: str):
    """Extracts the text content from a Markdown heading line."""
    return re.sub(r'^\s*#{1,6}\s+', '', line).strip()


def _is_table_line(line: str):
    """
    Checks if a line belongs to a Markdown table.
    A table line typically starts with `|` or contains multiple `|` separators.
    """
    s = (line or '').strip()
    if not s:
        return False
    if s.startswith('|'):
        return True
    if ('|' in s) and s.count('|') >= 2:
        return True
    return False


def _contains_table_keyword(text: str):
    """Checks if the text contains keywords 'table' or '表' (case-insensitive)."""
    t = (text or "").lower()
    return ('table' in t) or ('表' in t)


def enhance_table_titles(md_text: str) -> str:
    """
    Scans Markdown text to associate headings with subsequent tables.

    If a heading contains table keywords (e.g., "Table 1") and is followed by a table,
    the heading text is merged into the table structure or formatted to ensure association.

    Args:
        md_text (str): The input Markdown text.

    Returns:
        str: The processed Markdown text with enhanced table titles.
    """
    lines = md_text.split('\n')
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if _is_heading(line):
            heading_text = _get_heading_text(line)
            if _contains_table_keyword(heading_text):
                existing_caption = _detect_table_caption(heading_text)
                caption = None
                k = i + 1
                while k < n and (not lines[k].strip()):
                    k += 1
                start = None
                end = None
                if k < n and _is_table_line(lines[k]):
                    start = k
                    end = k
                    while end + 1 < n and _is_table_line(lines[end + 1]):
                        end += 1
                else:
                    start = k
                    end = k
                    while end < n and lines[end].strip() and not _is_heading(lines[end]) and lines[end] != '-' * 10:
                        if _is_table_line(lines[end]):
                            if start is None:
                                start = end
                            while end + 1 < n and _is_table_line(lines[end + 1]):
                                end += 1
                            break
                        end += 1
                    if start is None or not _is_table_line(lines[start]):
                        start = None
                        end = None
                if start is not None:
                    p = start - 1
                    while p >= 0 and not lines[p].strip():
                        p -= 1
                    prev_line = lines[p].strip() if p >= 0 else ''
                    caption = _detect_table_caption(prev_line) or caption
                    if caption is None:
                        q = end + 1
                        while q < n and not lines[q].strip():
                            q += 1
                        next_line = lines[q].strip() if q < n else ''
                        caption = _detect_table_caption(next_line)
                if caption and (existing_caption is None or existing_caption.lower() != caption.lower()):
                    new_heading_text = heading_text + '|' + caption
                    lines[i] = re.sub(r'^(\s*#{1,6}\s+).+$', r'\1' + new_heading_text, line)
        i += 1
    return '\n'.join(lines)