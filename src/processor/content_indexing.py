from typing import List, Tuple, Dict
import json
import re
import pickle
import os
import tempfile
from data.redis.cache_service import CacheService
from utils.minio_tool import MinioConnection

# 定义数据结构
# 把文章原始结构分为段落、行、span（最小语义单元）
# 经过观察，这个最小语义单元其实就是文本中的一行（如果是双栏布局，这个span就是一侧的行）
class SpanInfo:
    """
    定义span信息
    content: span的文本内容
    bbox: span的位置信息，[x0, y0, x1, y1]
    """
    def __init__(self, content: str, bbox: List[int]):  # 修改为List[int]
        self.content = content
        self.bbox = bbox
    
    def get_char_bbox(self, char_start: int, char_end: int) -> List[int]:
        """
        根据字符位置计算精确的bbox
        :param char_start: 字符开始位置（相对于span内容）
        :param char_end: 字符结束位置（相对于span内容）
        :return: 精确的bbox [x0, y0, x1, y1]
        """
        # 搜索范围有问题，返回当前bbox
        if char_start < 0 or char_end > len(self.content) or char_start >= char_end:
            return self.bbox
        
        # 计算字符在span中的相对位置比例
        total_chars = len(self.content)
        if total_chars == 0:
            return self.bbox
        # 这里其实就是计算字符在span中的相对位置比例
        start_ratio = char_start / total_chars
        end_ratio = char_end / total_chars
        
        # 基于比例计算精确的x坐标
        x0, y0, x1, y1 = self.bbox
        width = x1 - x0
        
        precise_x0 = int(x0 + width * start_ratio)
        precise_x1 = int(x0 + width * end_ratio)
        
        # y坐标保持不变，因为是同一行
        # 但是这里就得有一个前提”span必须是一行的内容“ 
        return [precise_x0, y0, precise_x1, y1]

class LineInfo:
    """
    保存行信息
    spans: 行内的span信息
    bbox: 行的位置信息，[x0, y0, x1, y1]
    """
    def __init__(self, spans: List[SpanInfo], bbox: List[int]):  # 修改为List[int]
        # 这里spans和span_indices是一一对应的
        # span_indices是span在行内的索引
        self.spans = spans # 语义单元span的集合
        self.bbox = bbox # 行的位置信息
        self.text = "".join(s.content for s in spans) # 整行内容
        self.span_indices = list(range(len(spans))) # 行内span的索引集合，其实也就是0到len(spans)-1

class ParaBlockInfo:
    def __init__(self, page_idx: int, block_type: str, bbox: List[int], lines: List[LineInfo]):  # 修改为List[int]
        self.page_idx = page_idx
        self.type = block_type
        self.bbox = bbox
        self.lines = lines
        # 这里把段落中每行的每个span都提取出来
        # 并给每个span分配一个索引
        self.spans = [s for line in lines for s in line.spans]
        # 这里是整段内容
        self.text = "".join(line.text for line in lines)
        # 
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

    def _build_ngram_index(self, max_ngram: int = 2) -> Dict[str, Tuple[int, int]]:
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

    def find_keyword(self, keyword: str, avoid_large_bbox: bool = True) -> List[Dict]:
        """
        功能：
        在段落中查找关键词，支持精确的字符级别定位
        实现方式：
        1. 直接在段落文本中查找关键词
        2. 找到关键词后，根据字符位置精确计算bbox
        3. 支持跨span的关键词匹配
        4. 可选择避免跨行时产生过大的bbox
        
        Args:
            keyword: 要查找的关键词
            avoid_large_bbox: 是否避免跨行时产生过大的bbox
        """
        matches = []
        # substring search on paragraph-level text
        # 在paragraph文本中查找关键词
        for match in re.finditer(re.escape(keyword), self.text):
            keyword_start = match.start()
            keyword_end = match.end()
            
            # 找到关键词跨越的所有span
            affected_spans: List[Dict] = []
            current_offset = 0
            
            for span_idx, span in enumerate(self.spans):
                span_start = current_offset
                span_end = current_offset + len(span.content)
                
                # 检查关键词是否与当前span有重叠
                if keyword_start < span_end and keyword_end > span_start:
                    # 计算关键词在当前span中的相对位置
                    char_start_in_span = max(0, keyword_start - span_start)
                    char_end_in_span = min(len(span.content), keyword_end - span_start)
                    
                    affected_spans.append({
                        'span_idx': span_idx,
                        'span': span,
                        'char_start': char_start_in_span,
                        'char_end': char_end_in_span
                    })
                
                current_offset = span_end
            
            if not affected_spans:
                continue
            
            # 计算精确的bbox
            precise_bboxes = []
            for span_info in affected_spans:
                span: SpanInfo = span_info['span']
                char_start = span_info['char_start']
                char_end = span_info['char_end']
                
                # 使用新的字符级别bbox计算方法
                precise_bbox = span.get_char_bbox(char_start, char_end)
                precise_bboxes.append(precise_bbox)
            
            # 处理bbox合并
            if len(precise_bboxes) == 1:
                # 只有一个bbox，直接使用，无需合并
                merged_bbox = precise_bboxes[0]
                is_cross_line = False
            elif avoid_large_bbox and len(precise_bboxes) > 1:
                # 使用智能分组避免过大的bbox
                separate_bboxes = self._get_separate_bboxes(precise_bboxes)
                if len(separate_bboxes) > 1:
                    # 返回多个独立的bbox
                    merged_bbox = separate_bboxes
                    is_cross_line = True
                else:
                    # 只有一个组，正常合并
                    merged_bbox = separate_bboxes[0] if separate_bboxes else [0, 0, 0, 0]
                    is_cross_line = False
            else:
                # 传统的合并方式（多个bbox）
                merged_bbox = self._merge_bboxes(precise_bboxes)
                is_cross_line = True
            
            result = {
                "page_idx": self.page_idx,
                "span_range": (affected_spans[0]['span_idx'], affected_spans[-1]['span_idx']),
                "bbox": merged_bbox,
                "keyword": keyword,
                "text_position": (keyword_start, keyword_end),
                "affected_spans": len(affected_spans)
            }
            
            # 只在avoid_large_bbox=True时添加is_cross_line字段
            if avoid_large_bbox:
                result['is_cross_line'] = is_cross_line
            
            matches.append(result)
        
        return matches
    
    @staticmethod
    def convert_bbox_from_points_to_pixels(bbox_pt: List[int], page_size_pt: List[int], target_dpi: int = 200) -> List[int]:  # 三处修改为List[int]
        ratio = target_dpi / 72.0
        x0, y0, x1, y1 = bbox_pt
        pw, ph = page_size_pt
        px0 = int(x0 * ratio)
        px1 = int(x1 * ratio)
        py0 = int((ph - y1) * ratio)
        py1 = int((ph - y0) * ratio)
        return [px0, py0, px1, py1]
 
    @staticmethod
    def _merge_bboxes(bboxes: List[List[int]]) -> List[int]:  # 两处修改为List[int]
        """合并bbox列表，但要避免跨行时产生过大的区域"""
        if not bboxes:
            return [0, 0, 0, 0]
        if len(bboxes) == 1:
            return bboxes[0]
        
        # 检查是否存在垂直分离的bbox（可能是跨行的情况）
        sorted_by_y = sorted(bboxes, key=lambda b: b[1])  # 按y0排序
        
        # 计算相邻bbox之间的垂直间距
        vertical_gaps = []
        for i in range(len(sorted_by_y) - 1):
            current_bottom = sorted_by_y[i][3]  # y1
            next_top = sorted_by_y[i + 1][1]    # y0
            gap = next_top - current_bottom
            vertical_gaps.append(gap)
        
        # 如果存在较大的垂直间距（可能是跨行），考虑分别处理
        max_gap = max(vertical_gaps) if vertical_gaps else 0
        avg_height = sum(b[3] - b[1] for b in bboxes) / len(bboxes)
        
        # 如果最大间距超过平均高度的一半，可能是跨行情况
        if max_gap > avg_height * 0.5:
            # 对于跨行情况，我们仍然返回合并的bbox，但在返回结果中添加警告信息
            # 实际应用中可以考虑返回多个独立的bbox
            pass
        
        # 执行标准的bbox合并
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        return [x0, y0, x1, y1]
    
    @staticmethod
    def _get_separate_bboxes(bboxes: List[List[int]], max_gap_ratio: float = 0.5) -> List[List[int]]:
        """将bbox列表分组，避免跨行时的大空白区域
        
        Args:
            bboxes: bbox列表
            max_gap_ratio: 最大间距与平均高度的比例阈值
            
        Returns:
            分组后的bbox列表，每组内的bbox会被合并
        """
        if not bboxes:
            return []
        if len(bboxes) == 1:
            return bboxes
        
        # 按y坐标排序
        sorted_bboxes = sorted(bboxes, key=lambda b: b[1])
        avg_height = sum(b[3] - b[1] for b in sorted_bboxes) / len(sorted_bboxes)
        
        # 分组bbox
        groups = []
        current_group = [sorted_bboxes[0]]
        
        for i in range(1, len(sorted_bboxes)):
            prev_bbox = sorted_bboxes[i-1]
            curr_bbox = sorted_bboxes[i]
            
            # 计算垂直间距
            gap = curr_bbox[1] - prev_bbox[3]
            
            # 如果间距太大，开始新的组
            if gap > avg_height * max_gap_ratio:
                groups.append(current_group)
                current_group = [curr_bbox]
            else:
                current_group.append(curr_bbox)
        
        groups.append(current_group)
        
        # 合并每组内的bbox
        result = []
        for group in groups:
            if len(group) == 1:
                result.append(group[0])
            else:
                x0 = min(b[0] for b in group)
                y0 = min(b[1] for b in group)
                x1 = max(b[2] for b in group)
                y1 = max(b[3] for b in group)
                result.append([x0, y0, x1, y1])
        
        return result

class DocumentIndex:
    def __init__(self, pages: Dict[int, List[ParaBlockInfo]]):
        self.pages: Dict[int, List[ParaBlockInfo]] = pages
    
    @staticmethod
    def from_middle_json(middle_json: Dict) -> "DocumentIndex":
        """
        从middle.json 构建 DocumentIndex 实例。
        将 JSON 数据解析与对象构造解耦，逻辑更清晰、易于测试与维护。
        """
        pages: Dict[int, List[ParaBlockInfo]] = {}
        for page in middle_json.get('pdf_info', []):
            idx = page.get('page_idx')
            para_list = []
            for blk in page.get('para_blocks', []):
                lines = []
                for line in blk.get('lines', []):
                    # 根据这一行对象的lineInfo提取所有的span对象
                    spans = [SpanInfo(s.get('content', ''), s.get('bbox')) for s in line.get('spans', [])]
                    lines.append(LineInfo(spans, line.get('bbox')))
                para_list.append(ParaBlockInfo(
                    page_idx=idx,
                    block_type=blk.get('type'),
                    bbox=blk.get('bbox'),
                    lines=lines
                ))
            pages[idx] = para_list
        return DocumentIndex(pages)

    def search(self, keyword: str) -> List[Dict]:
        results = []
        for blocks in self.pages.values():
            for pb in blocks:
                if keyword in pb.text:
                    results.extend(pb.find_keyword(keyword))
        return results

class DocumentIndexService:
    def __init__(self):
        self.cache_service = CacheService()
        self.minio_client = MinioConnection()

    def _find_middle_json_file(self, task_id: str, bucket_name: str) -> str:
        """
        查找指定任务ID的middle.json文件路径
        :param task_id: 任务ID
        :param bucket_name: OSS存储桶名称
        :return: middle.json文件路径
        """
        # 构建通配符模式
        pattern = f"{task_id}/*middle.json"
        
        # 查找匹配的文件
        matching_files = self.minio_client.find_files_by_pattern(bucket_name, pattern)
        
        if not matching_files:
            raise FileNotFoundError(f"middle.json not found for task {task_id} in bucket {bucket_name}")
        
        # 假设只有一个匹配文件，返回第一个
        return matching_files[0]
        
    def load_document_index_from_oss(self, task_id: str, bucket_name: str) -> bool:
        """
        从OSS下载middle.json文件，创建DocumentIndex对象并存入Redis
        :param task_id: 任务ID
        :param bucket_name: OSS存储桶名称
        :return: 是否成功
        """
        try:
            # 从OSS下载middle.json文件
            file_name = self._find_middle_json_file(task_id, bucket_name)
            # 检查文件是否存在
            if not file_name:
                raise FileNotFoundError(f"middle.json not found for task {task_id} in bucket {bucket_name}")
            
            # 下载文件到临时文件
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # 下载文件
            if not self.minio_client.download_file(file_name, bucket_name, temp_path):
                raise Exception(f"Failed to download middle.json for task {task_id}")
            
            # 读取JSON文件并创建DocumentIndex对象
            with open(temp_path, 'r', encoding='utf-8') as f:
                middle_json = json.load(f)
            
            document_index = DocumentIndex.from_middle_json(middle_json)
            
            # 序列化DocumentIndex对象并存入Redis
            serialized_data = pickle.dumps(document_index)
            redis_key = f"document_index:{task_id}"
            self.cache_service.set(redis_key, serialized_data)
            
            # 清理临时文件
            os.unlink(temp_path)
            
            return True
            
        except Exception as e:
            print(f"Error loading document index from OSS: {e}")
            return False

    def search_keyword_in_document(self, task_id: str, keyword: str) -> List[Dict]:
        """
        从Redis中获取DocumentIndex对象并搜索关键词
        :param task_id: 任务ID
        :param keyword: 要搜索的关键词
        :return: 搜索结果列表
        """
        try:
            # 从Redis获取序列化的DocumentIndex对象
            redis_key = f"document_index:{task_id}"
            serialized_data = self.cache_service.get(redis_key)
            
            if serialized_data is None:
                raise ValueError(f"No document index found for task {task_id}")
            
            # 反序列化DocumentIndex对象
            document_index: DocumentIndex = pickle.loads(serialized_data)
            
            # 搜索关键词
            results = document_index.search(keyword)
            
            return results
            
        except Exception as e:
            print(f"Error searching keyword in document: {e}")
            return []
# region
# Example usage 测试过程
if __name__ == '__main__':
    # 测试精确定位功能
    def test_precise_keyword_location():
        """测试字符级别的精确关键词定位"""
        print("=== 测试精确关键词定位功能 ===")
        
        # 创建测试数据
        span1 = SpanInfo("这是一个测试", [0, 0, 100, 20])
        span2 = SpanInfo("文档内容", [100, 0, 180, 20])
        span3 = SpanInfo("用于验证功能", [180, 0, 280, 20])
        
        line = LineInfo([span1, span2, span3], [0, 0, 280, 20])
        para = ParaBlockInfo(0, "text", [0, 0, 280, 20], [line])
        
        # 测试不同的关键词搜索
        test_cases = [
            ("测试", "应该精确定位到第一个span的部分区域"),
            ("文档", "应该精确定位到第二个span的部分区域"),
            ("内容用于", "应该跨越第二和第三个span"),
            ("一个测试文档", "应该跨越第一和第二个span")
        ]
        
        for keyword, description in test_cases:
            print(f"\n搜索关键词: '{keyword}' - {description}")
            # 测试传统方式
            results_traditional = para.find_keyword(keyword, avoid_large_bbox=False)
            print(f"  传统方式结果:")
            for i, result in enumerate(results_traditional):
                print(f"    结果 {i+1}:")
                print(f"      bbox: {result['bbox']}")
                print(f"      span范围: {result['span_range']}")
                print(f"      文本位置: {result['text_position']}")
                print(f"      影响的span数量: {result['affected_spans']}")
            
            # 测试智能分组方式
            results_smart = para.find_keyword(keyword, avoid_large_bbox=True)
            print(f"  智能分组方式结果:")
            for i, result in enumerate(results_smart):
                print(f"    结果 {i+1}:")
                print(f"      bbox: {result['bbox']}")
                print(f"      span范围: {result['span_range']}")
                print(f"      文本位置: {result['text_position']}")
                print(f"      影响的span数量: {result['affected_spans']}")
                print(f"      是否跨行: {result.get('is_cross_line', 'N/A')}")
        
        # 测试字符级别bbox计算
        print(f"\n=== 测试字符级别bbox计算 ===")
        test_span = SpanInfo("Hello World", [0, 0, 100, 20])
        
        # 测试不同的字符范围
        char_tests = [
            (0, 5, "Hello"),  # "Hello"
            (6, 11, "World"), # "World"
            (0, 11, "Hello World"), # 整个span
            (2, 8, "llo Wo")  # 中间部分
        ]
        
        for start, end, text in char_tests:
            bbox = test_span.get_char_bbox(start, end)
            print(f"  '{text}' ({start}-{end}): bbox = {bbox}")
    
    def test_cross_line_bbox_handling():
        """测试跨行bbox处理功能"""
        print("\n=== 测试跨行bbox处理功能 ===")
        
        # 创建跨行测试数据
        span1 = SpanInfo("上方行的关键", [10, 10, 120, 30])  # 上方行
        span2 = SpanInfo("词在这里继续", [10, 50, 120, 70])  # 下方行，有垂直间距
        
        line1 = LineInfo([span1], [10, 10, 120, 30])
        line2 = LineInfo([span2], [10, 50, 120, 70])
        para = ParaBlockInfo(0, "text", [10, 10, 120, 70], [line1, line2])
        
        keyword = "关键词"
        print(f"搜索跨行关键词: '{keyword}'")
        
        # 传统合并方式
        results_traditional = para.find_keyword(keyword, avoid_large_bbox=False)
        print("\n传统合并方式:")
        for result in results_traditional:
            bbox = result['bbox']
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            print(f"  bbox: {bbox}")
            print(f"  尺寸: 宽度={width}, 高度={height}")
        
        # 智能分组方式
        results_smart = para.find_keyword(keyword, avoid_large_bbox=True)
        print("\n智能分组方式:")
        for result in results_smart:
            print(f"  是否跨行: {result.get('is_cross_line', False)}")
            bbox = result['bbox']
            if isinstance(bbox[0], list):  # 多个bbox
                print(f"  分组数量: {len(bbox)}")
                for i, b in enumerate(bbox):
                    width = b[2] - b[0]
                    height = b[3] - b[1]
                    print(f"    组{i+1}: {b}, 尺寸: {width}x{height}")
            else:  # 单个bbox
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                print(f"  bbox: {bbox}")
                print(f"  尺寸: 宽度={width}, 高度={height}")
    
    # 运行原有测试
    try:
        with open('src/processor/middle.json', 'r', encoding='utf-8') as f:
            mj = json.load(f)
        doc_index = DocumentIndex.from_middle_json(mj)
        hits = doc_index.search("computational")
        print("\n=== 原有功能测试 ===")
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    except FileNotFoundError:
        print("\n=== middle.json文件未找到，跳过原有功能测试 ===")
    
    # 运行精确定位测试
    test_precise_keyword_location()
    
    # 运行跨行bbox处理测试
    test_cross_line_bbox_handling()
# endregion