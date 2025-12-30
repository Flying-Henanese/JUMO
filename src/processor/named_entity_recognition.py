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
import threading
from collections import OrderedDict
from typing import List, Dict, Any, Optional
from loguru import logger
from processor.nlp_inference.factory import InferenceFactory

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

    try:
        client = InferenceFactory.get_ner_client()
        return client.extract_entities(text, confidence_threshold, return_objects, entity_num)
    except Exception as e:
        logger.error(f"实体识别失败: {e}")
        return []

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