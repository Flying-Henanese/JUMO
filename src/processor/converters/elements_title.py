import re


def _detect_table_caption(text: str):
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
    return bool(re.match(r'^\s*#{1,6}\s+.+', line or ""))


def _get_heading_text(line: str):
    return re.sub(r'^\s*#{1,6}\s+', '', line).strip()


def _is_table_line(line: str):
    s = (line or '').strip()
    if not s:
        return False
    if s.startswith('|'):
        return True
    if ('|' in s) and s.count('|') >= 2:
        return True
    return False


def _contains_table_keyword(text: str):
    t = (text or "").lower()
    return ('table' in t) or ('表' in t)


def enhance_table_titles(md_text: str) -> str:
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