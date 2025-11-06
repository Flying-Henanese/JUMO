import pytest
import os
import sys
from typing import List, Dict, Any

# 添加src目录到Python路径，以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from processor.named_entity_recognition import (
    Entity, 
    SingletonNERModel, 
    extract_entities_auto,
    _chinese_ner_model,
    _english_ner_model,
    MODEL_NAME,
    ENGLISH_MODEL_NAME
)


class TestEntity:
    """测试Entity类"""
    
    def test_entity_creation(self):
        """测试实体创建"""
        entity = Entity(
            entity_group="PERSON",
            entity_text="张三",
            score=0.95,
            start=0,
            end=2
        )
        
        assert entity.entity_group == "PERSON"
        assert entity.entity_text == "张三"
        assert entity.score == 0.95
        assert entity.start == 0
        assert entity.end == 2
        assert entity.is_chinese == True
    
    def test_entity_text_cleaning(self):
        """测试实体文本清理"""
        # 测试中文实体（应去除空格）
        chinese_entity = Entity(
            entity_group="PERSON",
            entity_text="张 三",
            score=0.95,
            start=0,
            end=3
        )
        assert chinese_entity.entity_text == "张三"
        
        # 测试英文实体（应保留空格）
        english_entity = Entity(
            entity_group="PERSON",
            entity_text="John Smith",
            score=0.95,
            start=0,
            end=10
        )
        assert english_entity.entity_text == "John Smith"
        assert english_entity.is_chinese == False
    
    def test_entity_type_checkers(self):
        """测试实体类型检查方法"""
        person = Entity("PERSON", "张三", 0.95, 0, 2)
        org = Entity("ORG", "公司", 0.95, 0, 2)
        loc = Entity("LOC", "北京", 0.95, 0, 2)
        
        assert person.is_person() == True
        assert org.is_organization() == True
        assert loc.is_location() == True
    
    def test_entity_to_dict(self):
        """测试实体转换为字典"""
        entity = Entity("PERSON", "张三", 0.95, 0, 2)
        entity_dict = entity.to_dict()
        
        assert entity_dict['entity_group'] == "PERSON"
        assert entity_dict['entity'] == "张三"
        assert entity_dict['score'] == 0.95
        assert entity_dict['start'] == 0
        assert entity_dict['end'] == 2
        assert 'raw_entity' in entity_dict
        assert 'is_chinese' in entity_dict
    
    def test_entity_from_dict(self):
        """测试从字典创建实体"""
        data = {
            'entity_group': 'PERSON',
            'entity': '张三',
            'score': 0.95,
            'start': 0,
            'end': 2
        }
        
        entity = Entity.from_dict(data)
        assert entity.entity_group == "PERSON"
        assert entity.entity_text == "张三"
        assert entity.score == 0.95


class TestSingletonNERModel:
    """测试单例NER模型"""
    
    def test_model_singleton(self):
        """测试模型单例模式"""
        model1 = SingletonNERModel(MODEL_NAME)
        model2 = SingletonNERModel(MODEL_NAME)
        
        # 相同模型名称应返回同一个实例
        assert id(model1) == id(model2)
        
        # 不同模型名称应返回不同实例
        model3 = SingletonNERModel(ENGLISH_MODEL_NAME)
        assert id(model1) != id(model3)
    
    def test_model_initialization(self):
        """测试模型初始化"""
        model = SingletonNERModel(MODEL_NAME)
        
        assert model.model_name == MODEL_NAME
        assert model.tokenizer is not None
        assert model.model is not None
        assert model.ner_pipeline is not None


class TestExtractEntities:
    """测试实体提取功能"""
    
    def test_extract_chinese_entities(self):
        """测试中文实体提取"""
        chinese_text = "张三是北京大学的教授，他在清华大学工作。"
        entities = extract_entities_auto(chinese_text)
        
        assert isinstance(entities, list)
        assert len(entities) > 0
        
        # 检查返回的实体是否包含必要字段
        for entity in entities:
            assert 'entity_group' in entity
            assert 'entity' in entity
            assert 'score' in entity
            assert 'start' in entity
            assert 'end' in entity
    
    def test_extract_english_entities(self):
        """测试英文实体提取"""
        english_text = "Apple Inc. is a technology company founded by Steve Jobs in Cupertino, California."
        entities = extract_entities_auto(english_text)
        
        assert isinstance(entities, list)
        assert len(entities) > 0
        
        # 检查返回的实体是否包含必要字段
        for entity in entities:
            assert 'entity_group' in entity
            assert 'entity' in entity
            assert 'score' in entity
            assert 'start' in entity
            assert 'end' in entity
    
    def test_extract_entities_with_confidence_threshold(self):
        """测试使用置信度阈值提取实体"""
        text = "张三是北京大学的教授，他在清华大学工作。"
        
        # 使用高置信度阈值
        high_threshold_entities = extract_entities_auto(text, confidence_threshold=0.9)
        
        # 使用低置信度阈值
        low_threshold_entities = extract_entities_auto(text, confidence_threshold=0.1)
        
        # 低置信度阈值应该返回更多或相等的实体
        assert len(low_threshold_entities) >= len(high_threshold_entities)
    
    def test_extract_entities_with_limit(self):
        """测试限制实体数量"""
        text = "张三是北京大学的教授，他在清华大学工作。李四是上海复旦大学的讲师。"
        
        # 限制返回2个实体
        entities = extract_entities_auto(text, entity_num=2)
        
        assert len(entities) <= 2
    
    def test_extract_entities_return_objects(self):
        """测试返回Entity对象"""
        text = "张三是北京大学的教授。"
        
        # 返回Entity对象
        entities = extract_entities_auto(text, return_objects=True)
        
        assert len(entities) > 0
        assert isinstance(entities[0], Entity)
    
    def test_extract_empty_text(self):
        """测试空文本处理"""
        # 空字符串
        entities = extract_entities_auto("")
        assert entities == []
        
        # 只有空格的字符串
        entities = extract_entities_auto("   ")
        assert entities == []
    
    def test_extract_long_text(self):
        """测试长文本处理"""
        # 创建一个超过500字符的长文本
        long_text = "这是一个很长的文本。" * 100
        
        # 应该能够处理长文本而不出错
        entities = extract_entities_auto(long_text)
        assert isinstance(entities, list)


class TestModelSelection:
    """测试模型选择功能"""
    
    def test_chinese_text_detection(self):
        """测试中文文本检测"""
        from processor.named_entity_recognition import _is_chinese_text
        
        # 纯中文文本
        assert _is_chinese_text("这是中文文本") == True
        
        # 纯英文文本
        assert _is_chinese_text("This is English text") == False
        
        # 中英混合文本
        assert _is_chinese_text("这是中文 and English") == True
        
        # 空文本
        assert _is_chinese_text("") == False


class TestIntegration:
    """集成测试"""
    
    def test_end_to_end_chinese(self):
        """端到端中文测试"""
        text = "马云是阿里巴巴集团的创始人，公司总部位于杭州。"
        entities = extract_entities_auto(text)
        
        # 验证结果
        assert isinstance(entities, list)
        if len(entities) > 0:
            # 检查是否有预期的实体类型
            entity_groups = [e['entity_group'] for e in entities]
            # 支持标准NER标签和CLUEner2020标签体系
            expected_types = ['PERSON', 'ORG', 'LOC', 'name', 'company', 'organization', 'address']
            assert any(group in entity_groups for group in expected_types), f"未找到预期的实体类型，实际识别到的类型: {entity_groups}"
    
    def test_end_to_end_english(self):
        """端到端英文测试"""
        text = "Bill Gates founded Microsoft Corporation in Redmond, Washington."
        entities = extract_entities_auto(text)
        
        # 验证结果
        assert isinstance(entities, list)
        if len(entities) > 0:
            # 检查是否有预期的实体类型
            entity_groups = [e['entity_group'] for e in entities]
            assert any(group in entity_groups for group in ['PERSON', 'ORG', 'LOC'])


if __name__ == "__main__":
    # 直接运行此文件时执行测试
    pytest.main([__file__, "-v"])