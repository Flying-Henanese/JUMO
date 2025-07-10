from bs4 import BeautifulSoup
from mineru.backend.pipeline.batch_analyze import BatchAnalyze


def html_table_to_markdown(html: str) -> str:
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
    original_call = BatchAnalyze.__call__

    def patched_call(self, images_with_extra_info):
        results = original_call(self, images_with_extra_info)

        for layout_res in results:
            for item in layout_res:
                html = item.get('html')
                if html:
                    try:
                        md = html_table_to_markdown(html)
                        item['html'] = md  # 👈 替换 HTML 为 Markdown 表格
                    except Exception as e:
                        item['html'] = f'<!-- table conversion failed: {e} -->'

        return results

    BatchAnalyze.__call__ = patched_call
