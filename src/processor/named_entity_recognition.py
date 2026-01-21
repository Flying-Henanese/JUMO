"""
Named Entity Recognition (NER) Service
======================================

This module provides a robust service for extracting named entities (PERSON, ORGANIZATION, LOCATION, etc.)
from text. It supports both Chinese and English languages using pre-trained transformer models.

Key Features:
-------------
1.  **Multi-Language Support**:
    -   Automatically detects the language of the input text.
    -   Uses `uer/roberta-base-finetuned-cluener2020-chinese` for Chinese text.
    -   Uses `elastic/distilbert-base-cased-finetuned-conll03-english` for English text.

2.  **Singleton Model Loading**:
    -   Implements a thread-safe singleton pattern (`SingletonNERModel`) to ensure models are loaded only once
        and shared across requests, optimizing memory usage.
    -   Supports loading models onto different devices (CPU, CUDA, MPS, CANN).

3.  **Entity Standardization**:
    -   Maps model-specific labels (e.g., 'PER', 'ORG') to a unified set of standard types:
        `PERSON`, `ORGANIZATION`, `LOCATION`, `MISCELLANEOUS`.
    -   Provides the `Entity` class to encapsulate entity data with validation and cleaning logic.

4.  **Text Reconstruction**:
    -   Includes logic (`_reconstruct_entity_text_and_bounds`) to fix common tokenizer artifacts,
        such as merging split sub-words ("##") and correcting boundaries for English words.

Usage:
------
The primary entry point is `extract_entities_auto(text)`.
    >>> entities = extract_entities_auto("Apple is looking at buying U.K. startup for $1 billion")
    >>> print(entities)
    [{'entity_group': 'ORGANIZATION', 'entity': 'Apple', ...}, {'entity_group': 'LOCATION', 'entity': 'U.K.', ...}]
"""
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
import threading
from collections import OrderedDict
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import List, Dict, Any, Optional
from loguru import logger
from utils.auto_device_selector import get_device
from utils.singleton import parameterized_singleton
from transformers.pipelines import Pipeline
from transformers.modeling_utils import PreTrainedModel
from transformers.tokenization_utils_base import PreTrainedTokenizerBase

# 预设好NER模型的名称
MODEL_NAME = "uer/roberta-base-finetuned-cluener2020-chinese"
ENGLISH_MODEL_NAME = "dslim/bert-base-NER"#"elastic/distilbert-base-cased-finetuned-conll03-english"
# region
class Entity:
    """
    命名实体对象，用于存储NER识别出的实体信息
    支持CoNLL-03和CLUEner2020两种标签体系
    """
    
    # 标签映射：
    # 因为中英文两个NER模型的标签体系不太一样
    # 所以将不同模型的标签映射到统一的类别
    LABEL_MAPPINGS = {
        # 人名类别
        'PERSON': {'PERSON', 'PER', 'PEOPLE', 'name'},
        # 组织机构类别  
        'ORGANIZATION': {'ORG', 'ORGANIZATION', 'COMPANY', 'company', 'organization', 'government'},
        # 地点类别
        'LOCATION': {'LOC', 'LOCATION', 'PLACE', 'GPE', 'address', 'ADDRESS'},
        # 其他类别
        'MISCELLANEOUS': {'MISC', 'position', 'movie', 'game', 'book', 'scene'}
    }
    
    def __init__(self, 
                 entity_group: str, 
                 entity_text: str, 
                 score: float, 
                 start: int, 
                 end: int,
                 ):
        """
        初始化实体对象
        
        Args:
            entity_group (str): 实体类型/标签 (如: PERSON, ORG, LOC等)
            entity_text (str): 实体文本内容
            score (float): 置信度分数 (0-1之间)
            start (int): 在原文中的起始位置
            end (int): 在原文中的结束位置
        """
        self.entity_group: str = entity_group # NER模型输出的原始标签
        self._raw_entity_text: str = entity_text  # 保存原始文本
        self.score: float = round(score, 4) # 置信度分数 (0-1之间)
        self.start: int = start # 在原文中的起始位置
        self.end: int = end # 在原文中的结束位置
        
        # 检测是否为中文实体
        self.is_chinese: bool = self._detect_chinese(entity_text)
        
        # 获取标准化的实体类型
        self.standard_type: str = self._get_standard_type(entity_group)
        
        # 验证数据有效性
        self._validate()
    
    def _detect_chinese(self, text: str) -> bool:
        """
        检测文本是否包含中文字符
        
        Args:
            text: 要检测的文本
            
        Returns:
            bool: 如果包含中文字符返回True，否则返回False
        """
        return any('\u4e00' <= char <= '\u9fff' for char in text)
    
    def _get_standard_type(self, entity_group: str) -> str:
        """
        将原始标签映射到标准类型
        
        Args:
            entity_group: 原始实体标签
            
        Returns:
            str: 标准化的实体类型 (PERSON, ORGANIZATION, LOCATION, MISCELLANEOUS, UNKNOWN)
        """
        entity_group_upper = entity_group.upper()
        
        for standard_type, labels in self.LABEL_MAPPINGS.items():
            if entity_group_upper in {label.upper() for label in labels}:
                return standard_type
        
        return 'UNKNOWN'
    
    @property
    def entity_text(self) -> str:
        """
        获取清理后的实体文本
        
        - 中文实体：去除字符间的空格
        - 英文实体：保留正常空格，规范化多余空格
        
        Returns:
            str: 清理后的实体文本
        """
        return self._clean_entity_text(self._raw_entity_text)
    
    @property
    def raw_entity_text(self) -> str:
        """
        获取原始的实体文本（未经清理）
        
        Returns:
            str: 原始实体文本
        """
        return self._raw_entity_text
    
    def _validate(self):
        """验证实体数据的有效性"""
        if not self._raw_entity_text.strip():
            raise ValueError("实体文本不能为空")
        if not (0 <= self.score <= 1):
            raise ValueError(f"置信度分数必须在0-1之间，当前值: {self.score}")
        if self.start < 0 or self.end < 0:
            raise ValueError(f"位置索引不能为负数，start: {self.start}, end: {self.end}")
        if self.start >= self.end:
            raise ValueError(f"起始位置必须小于结束位置，start: {self.start}, end: {self.end}")
    
    def _clean_entity_text(self, text: str) -> str:
        """
        智能清理实体文本
        
        Args:
            text: 原始实体文本
            
        Returns:
            str: 清理后的实体文本
        """
        if not text:
            return text
        
        # 基础清理：去除首尾空格
        text = text.strip()
        
        if self.is_chinese:
            # 中文文本：去除所有空格（因为中文NER模型输出的空格通常是多余的）
            text = text.replace(' ', '')
        # 英文实体：保持原样，不做额外处理（连续空格在实体名称中极其罕见，故不做处理）
        return text
    
    def is_person(self) -> bool:
        """判断是否为人名实体"""
        return self.standard_type == 'PERSON'
    
    def is_organization(self) -> bool:
        """判断是否为组织机构实体"""
        return self.standard_type == 'ORGANIZATION'
    
    def is_location(self) -> bool:
        """判断是否为地点实体"""
        return self.standard_type == 'LOCATION'
    
    def is_miscellaneous(self) -> bool:
        """判断是否为其他杂项实体"""
        return self.standard_type == 'MISCELLANEOUS'
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，兼容现有API"""
        return {
            'entity_group': self.entity_group,
            'standard_type': self.standard_type,  # 添加标准化类型
            'entity': self.entity_text,  # 返回清理后的文本
            'raw_entity': self.raw_entity_text,  # 同时提供原始文本
            'is_chinese': self.is_chinese,  # 语言标识
            'score': self.score,
            'start': self.start,
            'end': self.end
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Entity':
        """从字典创建Entity对象"""
        # 优先使用raw_entity，如果没有则使用entity或word
        entity_text = data.get('raw_entity') or data.get('entity') or data.get('word', '')
        
        return cls(
            entity_group=data.get('entity_group', 'UNKNOWN'),
            entity_text=entity_text,
            score=data.get('score', 0),
            start=data.get('start', 0),
            end=data.get('end', 0)
        )
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"Entity('{self.entity_text}', {self.entity_group}, {self.score})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"Entity(entity_group='{self.entity_group}', "
                f"entity_text='{self.entity_text}', "
                f"score={self.score}, "
                f"start={self.start}, "
                f"end={self.end})")
    
    def __eq__(self, other) -> bool:
        """相等性比较"""
        if not isinstance(other, Entity):
            return False
        return (self.entity_group == other.entity_group and
                self.entity_text == other.entity_text
                )
    
    def __hash__(self) -> int:
        """哈希值，用于集合操作"""
        return hash((self.entity_group, self.entity_text))
# endregion

@parameterized_singleton(lambda model_name: model_name)
class SingletonNERModel:
    """
    使用单例模式的命名实体识别模型
    支持 MPS、CUDA 和 CANN 平台
    """
    
    def __init__(self, model_name: str = MODEL_NAME, device: Optional[str] = None):
        self.model_name: str = model_name
        self.device: str = get_device()
        self.tokenizer: Optional[PreTrainedTokenizerBase] = None
        self.model: Optional[PreTrainedModel] = None
        self.ner_pipeline: Optional[Pipeline] = None
        
        self._load_model()
    

    
    def _load_model(self):
        """
        加载模型和分词器
        """
        try:
            logger.info(f"正在加载NER模型: {self.model_name}")
            # 加载分词器
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            # 加载模型
            self.model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            
            # 将模型移动到指定设备
            if self.device != "cpu":
                try:
                    self.model = self.model.to(self.device)
                    logger.info(f"模型已移动到设备: {self.device}")
                except Exception as e:
                    logger.warning(f"无法将模型移动到 {self.device}，回退到CPU: {e}")
                    self.device = "cpu"
            
            # 创建pipeline
            self.ner_pipeline = pipeline(
                "ner", # 告诉transformers，这是个ner任务
                model=self.model, # 指定模型
                tokenizer=self.tokenizer, # 指定分词器
                # 指定设备;因为在上方已经使用model.to()方法将模型移动到指定设备，这里无需再指定
                # device=0 if self.device == "cuda" else -1, 

                # 当你希望拿到“自然语言级的实体”（而不是逐 token）用于业务逻辑、存储或展示，使用simple策略
                # 如果使用none，会返回所有识别到的token级别的实体,人类看不懂
                # 如果使用first，会返回每个实体的第一个token的位置，用于定位实体在原始文本中的位置
                # 如果使用max，会返回每个实体的所有token中置信度最高的那个token的位置
                # 综上，simple策略会将连续的实体合并为一个，而none策略会返回所有token级别的实体
                aggregation_strategy="simple" # 简单合并策略，将连续的实体合并为一个
            )
            
            logger.info("NER模型加载完成")
            
        except Exception as e:
            logger.error(f"加载NER模型失败: {e}")
            raise
    
    def extract_entities(self, 
                        text: str, 
                        confidence_threshold: float = 0.7, 
                        return_objects: bool = False, 
                        entity_num: int = 5
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取命名实体
        
        Args:
            text (str): 输入文本，长度建议在50-500字之间
            confidence_threshold (float): 置信度阈值，默认0.5
            return_objects (bool): 是否返回Entity对象，默认False返回字典
            entity_num (int): 返回的最大实体数量，默认5个
            
        Returns:
            List[Dict[str, Any]] 或 List[Entity]: 实体列表
            字典格式包含以下字段：
                - entity_group: 实体类型
                - entity: 实体文本
                - score: 置信度分数
                - start: 起始位置
                - end: 结束位置
        """
        if not text or not text.strip():
            logger.warning("输入文本为空")
            return []
        
        original_text = text.strip()
        text = original_text
        
        # 检查文本长度并进行截断
        # 这里虽然不能严格对应实际的512 tokens的长度
        # 但是可以应付绝大部分场景
        # 如果使用基于tokens的滑动窗口就有点复杂了
        # 现在 simply,lovely
        max_length = 500  # 保守的最大长度，确保分词后不超过512
        if len(text) > max_length:
            logger.warning(f"输入文本长度 {len(text)} 超过最大长度 {max_length}，将进行截断")
            text = text[:max_length]
        elif len(text) < 10:
            logger.warning(f"输入文本长度 {len(text)} 过短，可能影响识别效果")
        
        try:
            # 执行命名实体识别
            raw_entities = self.ner_pipeline(text)
            
            # 过滤低置信度的实体
            filtered_entities = [
                entity for entity in raw_entities 
                if entity.get('score', 0) >= confidence_threshold
            ]
            
            # 创建Entity对象或字典
            entities = []
            for entity_data in filtered_entities:
                # 使用独立函数重建更友好的实体文本与词边界
                # 避免出现识别出来的实体是一个被拆出来的子词（比如kagawa被识别成了#gawa）
                clean_text, left, right = _reconstruct_entity_text_and_bounds(original_text, entity_data)

                if return_objects:
                    entity_obj = Entity(
                        entity_group=entity_data.get('entity_group', 'UNKNOWN'),
                        entity_text=clean_text,
                        score=round(entity_data.get('score', 0), 4),
                        start=left,
                        end=right
                    )
                    entities.append(entity_obj)
                else:
                    entities.append({
                        'entity_group': entity_data.get('entity_group', 'UNKNOWN'),
                        'entity': clean_text,
                        'score': round(entity_data.get('score', 0), 4),
                        'start': left,
                        'end': right
                    })
            
            # 根据置信度对实体进行排序（降序排列）
            if return_objects:
                entities.sort(key=lambda x: x.score, reverse=True)
            else:
                entities.sort(key=lambda x: x['score'], reverse=True)

            # 使用有序集合去重并保留置信度最高的实体
            unique_entities = OrderedDict()
            for entity in entities:
                if return_objects:
                    entity_key = (entity.entity_group, entity.entity_text)
                else:
                    entity_key = (entity['entity_group'], entity['entity'])
                if entity_key not in unique_entities:
                    unique_entities[entity_key] = entity
                if len(unique_entities) >= entity_num:
                    break

            return list(unique_entities.values())
            
        except Exception as e:
            logger.error(f"实体识别失败: {e}")
            return []
    
    def get_entity_types(self, text: str, confidence_threshold: float = 0.5) -> List[str]:
        """
        获取文本中的实体类型列表
        
        Args:
            text (str): 输入文本
            confidence_threshold (float): 置信度阈值
            
        Returns:
            List[str]: 去重后的实体类型列表
        """
        entities = self.extract_entities(text, confidence_threshold)
        entity_types = list(set([entity['entity_group'] for entity in entities]))
        return sorted(entity_types)
    
    def get_entities_by_type(self, text: str, entity_type: str, confidence_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        获取指定类型的实体
        
        Args:
            text (str): 输入文本
            entity_type (str): 实体类型
            confidence_threshold (float): 置信度阈值
            
        Returns:
            List[Dict[str, Any]]: 指定类型的实体列表
        """
        entities = self.extract_entities(text, confidence_threshold)
        return [entity for entity in entities if entity['entity_group'] == entity_type]


# 全局模型实例 - 直接创建，无需延迟初始化
logger.info("初始化中文NER模型...")
_chinese_ner_model: SingletonNERModel = SingletonNERModel(MODEL_NAME)

logger.info("初始化英文NER模型...")
_english_ner_model: SingletonNERModel = SingletonNERModel(ENGLISH_MODEL_NAME)
_model_lock = threading.Lock()


def _is_chinese_text(text: str) -> bool:
    """
    简单的中文文本检测
    
    Args:
        text (str): 要检测的文本
        
    Returns:
        bool: 如果包含中文字符返回True，否则返回False
    """
    if not text:
        return False
    
    # 检查是否包含中文字符（Unicode范围：\u4e00-\u9fff）
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

# 模块级函数：_reconstruct_entity_text_and_bounds
def _reconstruct_entity_text_and_bounds(original_text: str, entity_data: Dict[str, Any]):
    """
    基于原文和 NER 输出的起止位置，重建更友好的实体文本：
    - 向左右扩展到完整英文单词边界（仅 ASCII 英文字母）
    - 去除 WordPiece 前缀“##”
    - 中文场景移除空格
    返回: (clean_text, left_idx, right_idx)
    """

    # 边界保护，获取原始段落的长度
    n = len(original_text)
    try:
        # 获取这个实体在原文中的起始索引
        start = max(0, int(entity_data.get('start', 0)))
        # 获取这个实体在原文中的结束索引
        end = min(n, int(entity_data.get('end', 0)))
    except Exception:
        start, end = 0, 0
    if start >= end:
        start, end = 0, 0

    # 仅在英文场景扩展词边界
    # 但是这个函数现在还很暴力
    def is_letter(ch: str) -> bool:
        allowed = "-_.&'’"
        return ch.isascii() and (ch.isalnum() or ch in allowed)

    left, right = start, end
    # 向左扩展到完整英文单词边界
    while left > 0 and is_letter(original_text[left - 1]):
        left -= 1
    # 向右扩展到完整英文单词边界
    while right < n and is_letter(original_text[right]):
        right += 1

    # 原文切片优先
    full_text = original_text[left:right].strip() if left < right else ""
    # 兜底使用 pipeline 的文本
    if not full_text:
        fallback = entity_data.get('raw_entity') or entity_data.get('entity') or entity_data.get('word') or ""
        full_text = str(fallback)

    # 清理 WordPiece 前缀
    full_text = full_text.replace("##", "")

    # 中文场景移除空格
    if _is_chinese_text(full_text):
        full_text = full_text.replace(" ", "")

    return full_text, left, right

def extract_entities_auto(text: str, confidence_threshold: float = 0.5, 
                         return_objects: bool = False, entity_num: int = 5) -> List[Dict[str, Any]]:
    """
    自动选择模型进行实体识别
    
    Args:
        text (str): 输入文本
        confidence_threshold (float): 置信度阈值，默认0.5
        return_objects (bool): 是否返回Entity对象，默认False返回字典
        entity_num (int): 返回的最大实体数量，默认5个
        
    Returns:
        List[Dict[str, Any]] 或 List[Entity]: 实体列表
    """
    if not text or not text.strip():
        logger.warning("输入文本为空")
        return []

    
    # 检测语言并选择对应模型
    if _is_chinese_text(text):
        logger.debug("检测到中文文本，使用中文模型")
        model: SingletonNERModel = _chinese_ner_model
    else:
        logger.debug("检测到英文文本，使用英文模型")
        model: SingletonNERModel = _english_ner_model
    
    # 调用对应模型进行实体识别
    return model.extract_entities(text, confidence_threshold, return_objects, entity_num)

def append_entities_to_header(header: str, chunk: str) -> str:
    """
    提取实体信息并将其添加到标题尾部。
    """
    processed_header = None
    try:
        entities: list[str] = [e.get('entity') for e in extract_entities_auto(chunk) if e.get('entity')]
        if header and entities:
            displayed_entities = ', '.join(entities)
            processed_header = f"{header} | ({displayed_entities})"
    except Exception as e:
        logger.warning(f"提取实体时发生异常: {e}")
    return processed_header if processed_header is not None else header