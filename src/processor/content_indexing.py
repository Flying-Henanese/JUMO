from typing import List, Tuple, Dict
import json
import re

# 定义数据结构
# 把文章原始结构分为段落、行、span（最小语义单元）
class SpanInfo:
    def __init__(self, content: str, bbox: List[float]):
        self.content = content
        self.bbox = bbox

class LineInfo:
    def __init__(self, spans: List[SpanInfo], bbox: List[float]):
        self.spans = spans
        self.bbox = bbox
        self.text = "".join(s.content for s in spans)
        self.span_indices = list(range(len(spans)))

class ParaBlockInfo:
    def __init__(self, page_idx: int, block_type: str, bbox: List[float], lines: List[LineInfo]):
        self.page_idx = page_idx
        self.type = block_type
        self.bbox = bbox
        self.lines = lines
        self.spans = [s for line in lines for s in line.spans]
        self.text = "".join(line.text for line in lines)
        self.span_to_char = self._build_span_offset_map()
        self.ngram_index = self._build_ngram_index()

    def _build_span_offset_map(self) -> Dict[int, Tuple[int, int]]:
        """
        为文本片段建立字符位置索引
        通过遍历self.spans列表，计算每个span的起始和结束字符位置
        最终输出一个字典，key为span索引，value为该span的字符起始和结束位置
        """
        span_to_char = {}
        offset = 0
        for i, span in enumerate(self.spans):
            start = offset
            offset += len(span.content)
            end = offset
            span_to_char[i] = (start, end)
        return span_to_char

    def _build_ngram_index(self, max_ngram: int = 3) -> Dict[str, Tuple[int, int]]:
        """
        功能：
        通过组合连续文本片段span生成短语索引
        实现方式：
        1. 遍历self.spans列表，生成所有可能的连续span组合
        2. 对每个组合，将span内容拼接成短语
        3. 将短语和其对应的span索引范围存入字典
        """
        idx = {} # 短语 -> span索引范围
        n = len(self.spans) # 获取span的数量
        for start in range(n): # 遍历所有的span
            phrase = "" # 约等于Java里的StringBuilder
            for end in range(start, min(n, start + max_ngram)):
                phrase += self.spans[end].content
                idx[phrase] = (start, end)
        return idx

    def find_keyword(self, keyword: str) -> List[Dict]:
        """
        功能：
        在段落中查找关键词
        实现方式：
        1. 直接在段落文本中查找关键词
        2. 找到关键词后，根据span索引范围确定关键词对应的span
        3. 合并关键词对应的span的bbox
        """
        matches = []
        # substring search on paragraph-level text
        # 在paragraph文本中查找关键词
        for match in re.finditer(re.escape(keyword), self.text):
            pos = match.start()
            start_span = end_span = None
            # find span indices that cover
            # span_index,(start,end)
            for si,(s,e) in self.span_to_char.items():
                # 如果找到了关键词所在的pos对应的span
                if s <= pos < e:
                    start_span = si
                if s < pos + len(keyword) <= e:
                    end_span = si
            if start_span is None or end_span is None:
                # 没有找到精确匹配的span
                # 退行到n-gram中查找
                if keyword in self.ngram_index:
                    start_span, end_span = self.ngram_index[keyword]
                else:
                    continue
            bboxes = [self.spans[i].bbox for i in range(start_span, end_span + 1)]
            merged = self._merge_bboxes(bboxes)
            matches.append({
                "page_idx": self.page_idx,
                "span_range": (start_span, end_span),
                "bbox": merged
            })
        return matches
    
    @staticmethod
    def convert_bbox_from_points_to_pixels(bbox_pt, page_size_pt, target_dpi=200):
        """
        把bbox从点单位转换为像素单位
        """
        ratio = target_dpi / 72.0
        x0, y0, x1, y1 = bbox_pt
        pw, ph = page_size_pt
        px0 = x0 * ratio
        px1 = x1 * ratio
        py0 = (ph - y1) * ratio
        py1 = (ph - y0) * ratio
        return [px0, py0, px1, py1]
    
    @staticmethod
    def _merge_bboxes(bboxes: List[List[float]]) -> List[float]:
        """
        合并多个bbox为一个
        取所有bbox中的最小x0,y0和最大x1,y1
        应对内容横跨多个行的情况
        """
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        return [x0, y0, x1, y1]

class DocumentIndex:
    def __init__(self, middle_json: Dict):
        self.pages: Dict[int, List[ParaBlockInfo]] = {}
        for page in middle_json.get('pdf_info', []):
            idx = page.get('page_idx')
            para_list = []
            for blk in page.get('para_blocks', []):
                lines = []
                for line in blk.get('lines', []):
                    spans = [SpanInfo(s.get('content', ''), s.get('bbox')) for s in line.get('spans', [])]
                    lines.append(LineInfo(spans, line.get('bbox')))
                para_list.append(ParaBlockInfo(idx, blk.get('type'), blk.get('bbox'), lines))
            self.pages[idx] = para_list

    def search(self, keyword: str) -> List[Dict]:
        results = []
        for blocks in self.pages.values():
            for pb in blocks:
                if keyword in pb.text:
                    results.extend(pb.find_keyword(keyword))
        return results

# Example usage
if __name__ == '__main__':
    with open('middle.json', 'r', encoding='utf-8') as f:
        mj = json.load(f)
    doc_index = DocumentIndex(mj)
    hits = doc_index.search("南京市长江大桥")
    print(json.dumps(hits, ensure_ascii=False, indent=2))