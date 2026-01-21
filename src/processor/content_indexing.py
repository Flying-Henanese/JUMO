"""
文档内容索引与搜索
====================================

本模块实现了一个用于索引和搜索结构化文档内容的系统。
它解析层级化的文档数据（页面 -> 段落 -> 行 -> 片段）并构建索引，
以支持带有坐标（边界框）检索的高效关键字搜索。

主要组件:
---------------
1.  **数据结构**:
    -   `SpanInfo`: 具有文本和边界框的最小语义单元。
    -   `LineInfo`: 由多个片段组成的文本行。
    -   `ParaBlockInfo`: 包含行的段落块，支持 n-gram 索引和关键字高亮。

2.  **DocumentIndex**:
    -   表示完整文档的内存索引。
    -   提供 `search` 方法以查找所有页面中的关键字出现位置。
    -   可以序列化/反序列化以进行缓存。

3.  **DocumentIndexService**:
    -   编排文档索引的生命周期。
    -   `load_document_index_from_oss`: 从 MinIO 下载 `middle.json`，将其解析为 `DocumentIndex`，并将其缓存到 Redis（Pickle 序列化）。
    -   `search_keyword_in_document`: 从 Redis 检索索引并执行搜索。

工作流程:
---------
1.  `PDFProcessor`（或类似组件）生成包含详细布局信息的 `middle.json`。
2.  `DocumentIndexService` 加载此 JSON，构建对象图，并将其缓存。
3.  客户端请求在文档中搜索关键字。
4.  服务获取缓存的索引并返回匹配的文本片段及其页面坐标。
"""
from typing import List, Tuple, Dict
import json
import re
import pickle
import os
import tempfile
import base64
from data.redis.cache_service import CacheService
from utils.minio_tool import MinioConnection

# 定义数据结构
# 把文章原始结构分为段落、行、span（最小语义单元）
class SpanInfo:
    """
    定义span信息
    content: span的文本内容
    bbox: span的位置信息，[x0, y0, x1, y1]
    """
    def __init__(self, content: str, bbox: List[int]):  # 修改为List[int]
        # 处理可能存在的转义字符，将 \" 替换为 "
        if isinstance(content, str):
            content = content.replace('\\"', '"')
        self.content = content
        self.bbox = bbox

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
        self.span_indices = list(range(len(spans))) # 行内span的索引集合

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
                # 如果找到了关键词所在的pos对应的span
                    # 单次遍历中同时查找 start_span 和 end_span
            for si, (s, e) in self.span_to_char.items():
                if start_span is None and s <= pos < e:
                    start_span = si
                if end_span is None and s < pos + len(keyword) <= e:
                    end_span = si
                if start_span is not None and end_span is not None:
                    break

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
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        return [x0, y0, x1, y1]

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
            # 使用base64编码避免特殊字符导致的问题
            serialized_data = base64.b64encode(pickle.dumps(document_index))
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
            # 兼容旧数据：尝试先base64解码，如果失败则假设是旧数据直接反序列化
            try:
                decoded_data = base64.b64decode(serialized_data)
                document_index: DocumentIndex = pickle.loads(decoded_data)
            except Exception:
                document_index: DocumentIndex = pickle.loads(serialized_data)
            
            # 搜索关键词
            results = document_index.search(keyword)
            
            return results
            
        except Exception as e:
            print(f"Error searching keyword in document: {e}")
            return []