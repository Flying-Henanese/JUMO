import os
import threading
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import List, Dict, Any, Optional
from loguru import logger
from utils.singleton import class_singleton
from transformers.pipelines import Pipeline
from transformers.modeling_utils import PreTrainedModel
from transformers.tokenization_utils_base import PreTrainedTokenizerBase



# 预设好NER模型的名称
MODEL_NAME = "uer/roberta-base-finetuned-cluener2020-chinese"

# region
class Entity:
    """
    命名实体对象，用于存储NER识别出的实体信息
    """
    def __init__(self, 
                 entity_group: str, 
                 entity_text: str, 
                 score: float, 
                 start: int, 
                 end: int,
                 source_text: Optional[str] = None):
        """
        初始化实体对象
        
        Args:
            entity_group (str): 实体类型/标签 (如: PERSON, ORG, LOC等)
            entity_text (str): 实体文本内容
            score (float): 置信度分数 (0-1之间)
            start (int): 在原文中的起始位置
            end (int): 在原文中的结束位置
            source_text (Optional[str]): 原始文本，用于验证和调试
        """
        self.entity_group = entity_group
        self.entity_text = entity_text.strip().replace(' ', '')
        self.score = round(score, 4)
        self.start = start
        self.end = end
        self.source_text = source_text
        
        # 验证数据有效性
        self._validate()
    
    def _validate(self):
        """验证实体数据的有效性"""
        if not self.entity_text:
            raise ValueError("实体文本不能为空")
        if not (0 <= self.score <= 1):
            raise ValueError(f"置信度分数必须在0-1之间，当前值: {self.score}")
        if self.start < 0 or self.end < 0:
            raise ValueError(f"位置索引不能为负数，start: {self.start}, end: {self.end}")
        if self.start >= self.end:
            raise ValueError(f"起始位置必须小于结束位置，start: {self.start}, end: {self.end}")
    
    def is_person(self) -> bool:
        """判断是否为人名实体"""
        return self.entity_group.upper() in ['PERSON', 'PER', 'PEOPLE']
    
    def is_organization(self) -> bool:
        """判断是否为组织机构实体"""
        return self.entity_group.upper() in ['ORG', 'ORGANIZATION', 'COMPANY']
    
    def is_location(self) -> bool:
        """判断是否为地点实体"""
        return self.entity_group.upper() in ['LOC', 'LOCATION', 'PLACE', 'GPE']
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，兼容现有API"""
        return {
            'entity_group': self.entity_group,
            'entity': self.entity_text,
            'score': self.score,
            'start': self.start,
            'end': self.end
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], source_text: Optional[str] = None) -> 'Entity':
        """从字典创建实体对象"""
        return cls(
            entity_group=data.get('entity_group', 'UNKNOWN'),
            entity_text=data.get('entity', data.get('word', '')),
            score=data.get('score', 0.0),
            start=data.get('start', 0),
            end=data.get('end', 0),
            source_text=source_text
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

@class_singleton
class SingletonNERModel:
    """
    使用单例模式的命名实体识别模型
    支持 MPS、CUDA 和 CANN 平台
    """
    
    def __init__(self, model_name: str = MODEL_NAME, device: Optional[str] = None):
        self.model_name: str = model_name
        self.device: str = self._get_optimal_device(device)
        self.tokenizer: Optional[PreTrainedTokenizerBase] = None
        self.model: Optional[PreTrainedModel] = None
        self.ner_pipeline: Optional[Pipeline] = None
        
        self._load_model()
    
    def _get_optimal_device(self, device: Optional[str] = None) -> str:
        """
        自动选择最优设备或使用指定设备
        支持 MPS、CUDA 和 CANN (NPU)
        """
        if device:
            return device
            
        # 检查环境变量中的设备模式
        # 格式: DEVICE_MODE=cuda:0,npu:0,mps,cpu
        device_mode = os.getenv("DEVICE_MODE", "auto").split(":")[0].lower()
        
        if device_mode == "auto":
            # 自动检测可用设备
            if torch.cuda.is_available():
                device = "cuda"
                logger.info("检测到CUDA设备，使用GPU加速")
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = "mps"
                logger.info("检测到MPS设备，使用Apple Silicon加速")
            elif hasattr(torch, 'npu') and torch.npu.is_available():
                device = "npu"
                logger.info("检测到NPU设备，使用华为昇腾加速")
            else:
                device = "cpu"
                logger.info("使用CPU进行推理")
        else:
            # 使用指定的设备模式
            if device_mode in ["mps", "cuda", "npu", "cpu"]:
                device = device_mode
                logger.info(f"使用指定设备: {device}")
            else:
                device = "cpu"
                logger.warning(f"未知设备模式 {device_mode}，回退到CPU")
        
        return device
    
    def _load_model(self):
        """
        加载模型和分词器
        """
        try:
            logger.info(f"正在加载NER模型: {self.model_name}")
            
            # 设置HuggingFace镜像（如果需要）
            if os.getenv('HF_ENDPOINT'):
                logger.info(f"使用HuggingFace站点: {os.getenv('HF_ENDPOINT')}")
            
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
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1,
                aggregation_strategy="simple"
            )
            
            logger.info("NER模型加载完成")
            
        except Exception as e:
            logger.error(f"加载NER模型失败: {e}")
            raise
    
    def extract_entities(self, text: str, confidence_threshold: float = 0.5, 
                        return_objects: bool = False, entity_num: int = 5) -> List[Dict[str, Any]]:
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
                if return_objects:
                    # 返回Entity对象
                    entity_obj = Entity.from_dict(entity_data, source_text=original_text)
                    entities.append(entity_obj)
                else:
                    # 返回字典格式（保持向后兼容）
                    entities.append({
                        'entity_group': entity_data.get('entity_group', 'UNKNOWN'),
                        'entity': entity_data.get('word', '').replace(' ', ''),
                        'score': round(entity_data.get('score', 0), 4),
                        'start': entity_data.get('start', 0),
                        'end': entity_data.get('end', 0)
                    })
            
            # 根据置信度对实体进行排序（降序排列）
            if return_objects:
                # 对于Entity对象，使用score属性排序
                entities.sort(key=lambda x: x.score, reverse=True)
            else:
                # 对于字典格式，使用score键排序
                entities.sort(key=lambda x: x['score'], reverse=True)
            
            # 去重并取前entity_num个不同的实体
            unique_entities = []
            seen_entities = set()
            
            for entity in entities:
                if return_objects:
                    # 对于Entity对象，使用__eq__方法进行去重
                    if entity not in seen_entities:
                        unique_entities.append(entity)
                        seen_entities.add(entity)
                else:
                    # 对于字典格式，使用(entity_group, entity)元组进行去重
                    entity_key = (entity['entity_group'], entity['entity'])
                    if entity_key not in seen_entities:
                        unique_entities.append(entity)
                        seen_entities.add(entity_key)
                
                # 如果达到最大数量限制，提前终止
                if len(unique_entities) >= entity_num:
                    break
            
            logger.info(f"识别到 {len(entities)} 个实体，过滤后保留 {len(unique_entities)} 个不同实体")
            return unique_entities
            
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


def get_ner_model(model_name: str = MODEL_NAME, device: Optional[str] = None) -> SingletonNERModel:
    """
    获取NER模型单例实例
    
    Args:
        model_name (str): 模型名称，默认使用中文NER模型
        device (str, optional): 指定设备，如果不指定则自动选择
        
    Returns:
        SingletonNERModel: NER模型实例
    """
    return SingletonNERModel(model_name=model_name, device=device)


# 便捷函数
def extract_entities_from_text(text: str, confidence_threshold: float = 0.5, 
                              model_name: str = MODEL_NAME, 
                              return_objects: bool = False) -> List[Dict[str, Any]]:
    """
    便捷函数：从文本中提取命名实体
    
    Args:
        text (str): 输入文本
        confidence_threshold (float): 置信度阈值，默认0.5
        model_name (str): 模型名称，默认使用全局MODEL_NAME
        return_objects (bool): 是否返回Entity对象，默认False返回字典
        
    Returns:
        List[Dict[str, Any]] 或 List[Entity]: 实体列表
    """
    ner_model = get_ner_model(model_name=model_name)
    return ner_model.extract_entities(text, confidence_threshold, return_objects)


def main():
    """
    测试函数，演示Entity对象的使用
    """
    # 测试文本
    text = """
    张三是北京大学的教授，他在清华大学获得了博士学位。
    他的研究领域是人工智能，曾在微软亚洲研究院工作过。
    现在他住在北京市海淀区，经常去中关村参加技术交流会。
    """
    
    print("=== 命名实体识别测试 ===")
    print(f"输入文本: {text.strip()}")
    print()
    
    # 获取NER模型
    ner_model = get_ner_model()
    
    # 测试返回字典格式（向后兼容）
    print("1. 字典格式结果:")
    dict_entities = ner_model.extract_entities(text, confidence_threshold=0.3, return_objects=False)
    for i, entity in enumerate(dict_entities, 1):
        print(f"  {i}. {entity}")
    print()
    
    # 测试返回Entity对象
    print("2. Entity对象格式结果:")
    entity_objects = ner_model.extract_entities(text, confidence_threshold=0.3, return_objects=True)
    for i, entity in enumerate(entity_objects, 1):
        print(f"  {i}. {entity}")
        print(f"     - 类型判断: 人名={entity.is_person()}, 组织={entity.is_organization()}, 地点={entity.is_location()}")
    print()
    
    # 测试实体类型获取
    print("3. 实体类型:")
    entity_types = ner_model.get_entity_types(text)
    print(f"  发现的实体类型: {entity_types}")
    print()
    
    # 测试按类型筛选
    if entity_types:
        first_type = entity_types[0]
        print(f"4. '{first_type}' 类型的实体:")
        type_entities = ner_model.get_entities_by_type(text, first_type)
        for entity in type_entities:
            print(f"  - {entity}")
    
    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    main()