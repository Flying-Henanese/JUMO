#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试标签整合系统
验证Entity类能否正确处理CoNLL-03和CLUEner2020两种标签体系
"""

import pytest
import sys
import os
# 添加src目录到Python路径，以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from processor.named_entity_recognition import Entity, extract_entities_auto

class TestLabelIntegration:
    """测试标签整合系统"""
    
    def test_label_mappings(self):
        """测试标签映射功能"""
        print("=== 测试标签映射功能 ===")
        
        # 测试CoNLL-03标签
        conll_entities = [
            Entity("PER", "John Smith", 0.95, 0, 10),
            Entity("ORG", "Microsoft", 0.90, 15, 24),
            Entity("LOC", "New York", 0.88, 30, 38),
            Entity("MISC", "Nobel Prize", 0.85, 45, 55)
        ]
        
        # 测试CLUEner2020标签
        clue_entities = [
            Entity("name", "马云", 0.95, 0, 2),
            Entity("company", "阿里巴巴", 0.92, 5, 9),
            Entity("address", "杭州", 0.88, 15, 17),
            Entity("position", "CEO", 0.85, 20, 23)
        ]
        
        print("CoNLL-03标签测试:")
        for entity in conll_entities:
            print(f"  {entity.entity_text} ({entity.entity_group}) -> {entity.standard_type}")
            print(f"    人名: {entity.is_person()}, 组织: {entity.is_organization()}, 地点: {entity.is_location()}")
        
        print("\nCLUEner2020标签测试:")
        for entity in clue_entities:
            print(f"  {entity.entity_text} ({entity.entity_group}) -> {entity.standard_type}")
            print(f"    人名: {entity.is_person()}, 组织: {entity.is_organization()}, 地点: {entity.is_location()}")
        
        # 添加断言验证CoNLL-03标签映射
        assert conll_entities[0].standard_type == "PERSON"
        assert conll_entities[0].is_person() == True
        assert conll_entities[1].standard_type == "ORGANIZATION" 
        assert conll_entities[1].is_organization() == True
        assert conll_entities[2].standard_type == "LOCATION"
        assert conll_entities[2].is_location() == True
        assert conll_entities[3].standard_type == "MISCELLANEOUS"
        assert conll_entities[3].is_miscellaneous() == True
        
        # 添加断言验证CLUEner2020标签映射
        assert clue_entities[0].standard_type == "PERSON"
        assert clue_entities[0].is_person() == True
        assert clue_entities[1].standard_type == "ORGANIZATION"
        assert clue_entities[1].is_organization() == True
        assert clue_entities[2].standard_type == "LOCATION"
        assert clue_entities[2].is_location() == True
        assert clue_entities[3].standard_type == "MISCELLANEOUS"
        assert clue_entities[3].is_miscellaneous() == True

    def test_real_ner(self):
        """测试真实NER识别"""
        print("\n=== 测试真实NER识别 ===")
        
        # 测试中文文本
        chinese_text = "马云是阿里巴巴集团的创始人，公司总部位于杭州。"
        print(f"中文文本: {chinese_text}")
        
        chinese_entities = extract_entities_auto(chinese_text, return_objects=True)
        print("识别结果:")
        for entity in chinese_entities:
            if hasattr(entity, 'standard_type'):
                print(f"  {entity.entity_text} ({entity.entity_group} -> {entity.standard_type})")
                print(f"    人名: {entity.is_person()}, 组织: {entity.is_organization()}, 地点: {entity.is_location()}")
            else:
                print(f"  {entity}")
        
        # 断言：应该识别出至少一个实体
        assert len(chinese_entities) > 0, "中文文本应该识别出至少一个实体"
        
        # 断言：所有实体都应该有standard_type属性
        for entity in chinese_entities:
            assert hasattr(entity, 'standard_type'), f"实体 {entity} 缺少 standard_type 属性"
            assert hasattr(entity, 'is_person'), f"实体 {entity} 缺少 is_person 方法"
            assert hasattr(entity, 'is_organization'), f"实体 {entity} 缺少 is_organization 方法"
            assert hasattr(entity, 'is_location'), f"实体 {entity} 缺少 is_location 方法"
        
        # 测试英文文本
        english_text = "Apple Inc. was founded by Steve Jobs in Cupertino, California."
        print(f"\n英文文本: {english_text}")
        
        english_entities = extract_entities_auto(english_text, return_objects=True)
        print("识别结果:")
        for entity in english_entities:
            if hasattr(entity, 'standard_type'):
                print(f"  {entity.entity_text} ({entity.entity_group} -> {entity.standard_type})")
                print(f"    人名: {entity.is_person()}, 组织: {entity.is_organization()}, 地点: {entity.is_location()}")
            else:
                print(f"  {entity}")
        
        # 断言：应该识别出至少一个实体
        assert len(english_entities) > 0, "英文文本应该识别出至少一个实体"
        
        # 断言：所有实体都应该有standard_type属性
        for entity in english_entities:
            assert hasattr(entity, 'standard_type'), f"实体 {entity} 缺少 standard_type 属性"

    def test_compatibility(self):
        """测试兼容性 - 验证原有测试用例能够通过"""
        print("\n=== 测试兼容性 ===")
        
        # 测试原有测试用例是否仍然通过
        chinese_text = "马云是阿里巴巴集团的创始人，公司总部位于杭州。"
        entities = extract_entities_auto(chinese_text, return_objects=True)
        
        # 检查是否有预期的实体类型
        entity_groups = [entity.entity_group for entity in entities if hasattr(entity, 'entity_group')]
        standard_types = [entity.standard_type for entity in entities if hasattr(entity, 'standard_type')]
        
        print(f"原始标签: {entity_groups}")
        print(f"标准类型: {standard_types}")
        
        # 检查是否包含人名、组织或地点
        has_person = any(entity.is_person() for entity in entities if hasattr(entity, 'is_person'))
        has_org = any(entity.is_organization() for entity in entities if hasattr(entity, 'is_organization'))
        has_loc = any(entity.is_location() for entity in entities if hasattr(entity, 'is_location'))
        
        print(f"包含人名: {has_person}, 包含组织: {has_org}, 包含地点: {has_loc}")
        
        # 这应该解决原来的测试失败问题
        expected_found = has_person or has_org or has_loc
        print(f"测试应该通过: {expected_found}")
        
        # 添加断言：至少应该识别出人名、组织或地点中的一种
        assert expected_found, f"未找到预期的实体类型，实际识别到的实体: {[(e.entity_text, e.entity_group, e.standard_type) for e in entities]}"
        
        # 验证标准类型映射的正确性
        for entity in entities:
            # 确保每个实体都有标准类型
            assert hasattr(entity, 'standard_type'), f"实体 {entity.entity_text} 缺少 standard_type 属性"
            assert entity.standard_type in ['PERSON', 'ORGANIZATION', 'LOCATION', 'MISCELLANEOUS', 'UNKNOWN'], \
                f"实体 {entity.entity_text} 的标准类型 {entity.standard_type} 不在预期范围内"

if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])