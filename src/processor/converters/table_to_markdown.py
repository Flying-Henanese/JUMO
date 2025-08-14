from bs4 import BeautifulSoup
from mineru.backend.pipeline.batch_analyze import BatchAnalyze
from loguru import logger

def html_table_to_markdown(html: str) -> str:
    """
    将HTML表格转换为Markdown格式的具体行为
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
