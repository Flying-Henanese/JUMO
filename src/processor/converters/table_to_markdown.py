"""
HTML Table to Markdown Converter
================================

This module handles the conversion of HTML table structures into Markdown tables.
It is often used as a post-processing step for OCR or layout analysis tools that output HTML tables.

Key Features:
-------------
-   **`html_table_to_markdown`**: Parses HTML string and converts `<table>` tags to Markdown pipe tables.
-   **`html_table_to_key_value`**: Parses HTML string and converts `<table>` tags to key-value pair strings.
-   **`patch_batchanalyze_output_to_markdown`**: Monkey-patches the `BatchAnalyze` class from `mineru`
    to automatically convert its HTML table output to Markdown.
"""
from typing import List
from bs4 import BeautifulSoup
from mineru.backend.pipeline.batch_analyze import BatchAnalyze
from loguru import logger

def html_table_to_markdown(html: str) -> str:
    """
    将HTML表格转换为Markdown格式的具体实现
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if table is None:
        return ''

    rows = table.find_all('tr')
    if not rows:
        return ''

    markdown_lines = []
    header_cells = rows[0].find_all(['th', 'td'])
    header = [cell.get_text(strip=True) for cell in header_cells]
    markdown_lines.append('| ' + ' | '.join(header) + ' |')
    markdown_lines.append('|' + '|'.join([' --- ' for _ in header]) + '|')

    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        line = '| ' + ' | '.join(cell.get_text(strip=True) for cell in cells) + ' |'
        markdown_lines.append(line)

    return '\n'.join(markdown_lines)


def html_table_to_key_value(html: str) -> List[str]:
    """
    将HTML表格转换为键值对格式的列表
    处理了rowspan和colspan，将合并单元格的值填充到所有覆盖的网格中
    格式：['列名1：值1；列名2：值2；...', ...]
    默认第一行为标题行
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if table is None:
        return []

    rows = table.find_all('tr')
    if not rows:
        return []

    # 1. 预计算表格维度，构建网格
    # 虽然可以直接动态扩展，但为了方便，我们先估算最大列数（可选），或者动态管理
    # 这里采用动态填充的方式，使用一个二维字典或列表列表来模拟网格
    # grid[row_idx][col_idx] = value
    
    grid = []
    
    for r_idx, row in enumerate(rows):
        # 确保当前行在grid中存在
        while len(grid) <= r_idx:
            grid.append([])
            
        cells = row.find_all(['td', 'th'])
        c_idx = 0 # 当前行的列指针
        
        for cell in cells:
            # 跳过已经被上一行的rowspan占据的位置
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1
                
            # 获取当前单元格的文本值
            text = cell.get_text(strip=True)
            
            # 获取跨行跨列属性
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # 填充网格
            for r in range(rowspan):
                target_r = r_idx + r
                # 确保目标行存在
                while len(grid) <= target_r:
                    grid.append([])
                    
                for c in range(colspan):
                    target_c = c_idx + c
                    # 确保目标列位置在列表中存在（填充None占位）
                    while len(grid[target_r]) <= target_c:
                        grid[target_r].append(None)
                        
                    grid[target_r][target_c] = text
            
            # 移动列指针
            c_idx += colspan

    # 2. 提取标题和数据
    if not grid:
        return []
        
    # 假设第一行处理后的网格行是标题
    headers = grid[0]
    # 清理headers中的None值（虽然逻辑上不应该有，但为了健壮性）
    headers = [h if h is not None else "" for h in headers]
    
    kv_lines = []
    
    # 遍历数据行（从第二行开始）
    for row_values in grid[1:]:
        # 确保当前行长度与标题一致，取较小值
        min_len = min(len(headers), len(row_values))
        
        row_parts = []
        for i in range(min_len):
            key = headers[i]
            # row_values[i] 可能为 None (如果HTML结构不规整)，处理为 ""
            val = row_values[i] if row_values[i] is not None else ""
            
            # 只有当key存在时才生成键值对（避免无意义的列）
            if key:
                row_parts.append(f"{key}：{val}")
            
        if row_parts:
            kv_lines.append("；".join(row_parts) + "；")
            
    return kv_lines


def patch_batchanalyze_output_to_markdown():
    """
    给BatchAnalyze的__call__方法添加一个补丁，将html表格转换为markdown表格
    这样的话，在调用BatchAnalyze后，直接获取到的结果就是markdown格式的表格了
    """
    original_call = BatchAnalyze.__call__

    def patched_call(self, images_with_extra_info):
        results = original_call(self, images_with_extra_info)

        for layout_res in results:
            for item in layout_res:
                html = item.get('html')
                if html:
                    try:
                        md = html_table_to_markdown(html)
                        item['html'] = md 
                    except Exception as e:
                        logger.error(f"表格转换失败: {e}")
                        item['html'] = f'<!-- table conversion failed: {e} -->'

        return results

    BatchAnalyze.__call__ = patched_call


if __name__ == '__main__':

    print("-" * 20)
    print("Testing Rowspan:")
    rowspan_html = """
    <table>
        <tr>
            <th>Name</th>
            <th>Details</th>
        </tr>
        <tr>
            <td rowspan="2">Alice</td>
            <td>Age: 25</td>
        </tr>
        <tr>
            <td>City: New York</td>
        </tr>
        <tr>
            <td>Bob</td>
            <td>Age: 30</td>
        </tr>
    </table>
    """
    rowspan_records = html_table_to_key_value(rowspan_html)
    for r in rowspan_records:
        print(r)
