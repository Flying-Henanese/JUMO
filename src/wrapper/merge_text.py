from mineru.backend.pipeline.para_split import __merge_2_list_blocks as original_merge
from mineru.backend.pipeline.para_split import SplitFlag  # 确保导入原始常量

def safe_merge_2_list_blocks(block1, block2):
    """安全版本的合并函数，处理缺失字段"""
    # 确保 blocks 有必要的结构
    block1.setdefault('lines', [])
    block2.setdefault('lines', [])
    
    # 处理跨页标记（添加防御性检查）
    if block1.get('page_num') != block2.get('page_num'):
        for line in block1['lines']:
            for span in line.get('spans', []):
                span[SplitFlag.CROSS_PAGE] = True  # 假设 SplitFlag 已定义
    
    # 合并逻辑（保持原行为）
    block2['lines'].extend(block1['lines'])
    block1['lines'] = []
    block1[SplitFlag.LINES_DELETED] = True
    
    return block1, block2

def safe_merge_2_text_blocks(block1, block2):
    """修复 content 缺失问题的合并函数"""
    # 确保 blocks 和 spans 结构完整
    for block in [block1, block2]:
        block.setdefault('lines', [])
        for line in block['lines']:
            line.setdefault('spans', [])
            for span in line['spans']:
                if 'content' not in span:
                    span['content'] = ''  # 或根据 span['type'] 设置默认值
    
    # 调用原始合并逻辑
    return original_merge(block1, block2)