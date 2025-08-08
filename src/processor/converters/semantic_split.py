from typing import Any, Dict, List, Optional, Union

import torch
import tqdm
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from transformers import AutoTokenizer

from utils.logging import AppLogger

logger = AppLogger.get_logger(__name__)


class DocumentChunker:
    """
    文档分块处理器，将文档分割为有意义的文本块

    功能：
    1. 加载预训练的分词器和分块模型
    2. 读取并转换多种格式的文档
    3. 使用混合策略进行文档分块
    4. 提供分块结果和统计信息
    """

    def __init__(
        self, model_path: str, max_tokens: int = 1024, merge_peers: bool = True
    ):
        """
        初始化分块处理器

        :param model_path: 预训练模型路径
        :param max_tokens: 每个分块的最大token数，默认1024
        :param merge_peers: 是否合并同级内容，默认True
        """
        self.model_path = model_path
        self.max_tokens = max_tokens
        self.merge_peers = merge_peers

        # 初始化组件
        self.tokenizer = None
        self.chunker = None
        # 初始化文档转换工具
        self.converter = None
        self._initialize_components()

    def _initialize_components(self):
        """初始化分词器和分块器"""
        device = "cuda" if torch.cuda.is_available() else "cpu"
        device = (
            "mps" if torch.backends.mps.is_available() else device
        )  # For Mac users with MPS support
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True
        )

        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=self.max_tokens,
            merge_peers=self.merge_peers,
        )
        self.converter = DocumentConverter()

    def load_document(
        self, content: Union[str, bytes, Any], content_type: Optional[str] = None
    ) -> Any:
        """
        加载文档内容

        现在支持：
        - 直接传入文本字符串
        - 传入文件路径(向后兼容)
        - 传入二进制内容(需指定content_type)

        :param content: 文本内容或文件路径
        :param content_type: 内容类型，如'markdown'、'html'等
        :return: 转换后的文档对象
        """
        # 如果content是字符串且是文件路径(简单判断)
        if (
            isinstance(content, str)
            and "\n" not in content
            and len(content) < 256
            and content.endswith((".md", ".txt"))
        ):
            # 保持向后兼容，当作文件路径处理
            return self.converter.convert(source=content).document

        # 处理直接传入的文本内容
        if content_type:
            # 如果有明确的内容类型
            return self.converter.convert(
                source=content, content_type=content_type
            ).document
        else:
            # 默认当作markdown处理
            return self.converter.convert(
                source=content, content_type="markdown"
            ).document

    def chunk_document(
        self, document: Any, show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        执行文档分块处理

        :param document: 文档对象
        :param show_progress: 是否显示进度条
        :return: 分块结果列表，每个元素包含内容和元数据
        """
        chunk_iter = self.chunker.chunk(dl_doc=document)
        chunks = list(chunk_iter)

        results = []
        chunk_iterable = (
            tqdm.tqdm(enumerate(chunks)) if show_progress else enumerate(chunks)
        )

        for i, chunk in chunk_iterable:
            serialized_text = self.chunker.contextualize(chunk=chunk)
            token_count = len(self.tokenizer.tokenize(serialized_text))

            results.append(
                {
                    "chunk_id": i,
                    "content": serialized_text,
                    "token_count": token_count,
                    "metadata": {
                        "start_position": getattr(chunk, "start_pos", None),
                        "end_position": getattr(chunk, "end_pos", None),
                    },
                }
            )

        return results

    def process_file(
        self, file_content: str, show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        完整处理流程：加载文档并分块

        :param file_content: 文档内容
        :param show_progress: 是否显示进度条
        :return: 分块结果列表
        """
        document = self.load_document(file_content)
        return self.chunk_document(document, show_progress)

# region
# if __name__ == "__main__":
#     # 处理文档
#     chunker = DocumentChunker(
#         model_path="../models/text-seg-lm-qwen2-0.5b-cot-topic-chunking",
#         max_tokens=1024,
#     )
#     results = chunker.process_file("README.md")
#     with open("./output.md", "w", encoding="utf-8") as f:
#         for index, result in enumerate(results):
#             f.write(f'{result["content"]} +\n')
#             f.write(f"# 分割线 {index} \n")
# endregion
