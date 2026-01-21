"""
HTML 表格转 Markdown 转换器
================================

本模块负责将 HTML 表格结构转换为 Markdown 表格。
它通常用作 OCR 或布局分析工具（输出 HTML 表格）的后处理步骤。

主要功能:
-------------
-   **`html_table_to_markdown`**: 解析 HTML 字符串并将 `<table>` 标签转换为 Markdown 管道表格。
-   **`html_table_to_key_value`**: 解析 HTML 字符串并将 `<table>` 标签转换为键值对字符串。
-   **`patch_batchanalyze_output_to_markdown`**: 对 `mineru` 中的 `BatchAnalyze` 类进行 Monkey Patch，
    以自动将其 HTML 表格输出转换为 Markdown。
"""
from typing import List
from bs4 import BeautifulSoup
from mineru.backend.pipeline.batch_analyze import BatchAnalyze
from loguru import logger

def html_table_to_markdown(html: str) -> str:
    """
    将HTML表格转换为Markdown格式的具体实现
    
    逻辑概述：
    1. 构建虚拟网格：预先创建一个二维列表，用于模拟表格布局。
    2. 处理合并单元格：遍历HTML行时，若遇到rowspan/colspan，则将单元格内容“平铺”填充到网格中对应的所有坐标位置。
    3. 跳过已占位：遍历过程中，若发现当前网格位置已被上方单元格（因rowspan）占用，则自动跳过，确保数据对齐。
    4. 生成Markdown：最后基于填充完整的规则网格生成标准Markdown表格。
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if table is None:
        return ''

    rows = table.find_all('tr')
    if not rows:
        return ''

    # 1. 预计算表格维度，构建网格
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
            # Markdown表格中不能有换行符，替换为空格
            text = text.replace('\n', ' ')
            
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
                    
                    # 只有左上角的单元格填写真实值，其他合并位置可以填空字符串或相同值
                    # 为了Markdown表格完整性，建议填充相同值
                    grid[target_r][target_c] = text
            
            # 移动列指针
            c_idx += colspan

    if not grid:
        return ''

    # 2. 生成Markdown
    markdown_lines = []
    
    # 确保每一行长度一致（取最大列数）
    max_cols = max(len(r) for r in grid)
    for r in grid:
        while len(r) < max_cols:
            r.append("")

    # 表头
    header = grid[0]
    # 处理None值
    header = [h if h is not None else "" for h in header]
    markdown_lines.append('| ' + ' | '.join(header) + ' |')
    
    # 分隔线
    markdown_lines.append('|' + '|'.join([' --- ' for _ in range(max_cols)]) + '|')

    # 数据行
    for row in grid[1:]:
        # 处理None值
        row_clean = [cell if cell is not None else "" for cell in row]
        line = '| ' + ' | '.join(row_clean) + ' |'
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

# region
# 暂时先不使用这个补丁
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
# endregion

if __name__ == '__main__':

    print("-" * 20)
    print("Testing Rowspan:")
    rowspan_html = ""
    rowspan_records = html_table_to_markdown(rowspan_html)
    #rowspan_records = "\n".join(rowspan_records)
    with open('rowspan.md', 'w', encoding='utf-8') as f:
        f.write(rowspan_records)
    print(f'表格已经保存到 rowspan.md')
