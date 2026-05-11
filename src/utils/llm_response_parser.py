import json
import re
import logging

logger = logging.getLogger(__name__)

def try_parse_json(json_str: str) -> dict:
    """尝试解析 JSON 字符串，失败返回 None"""
    if not json_str or not json_str.strip():
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

def basic_json_cleanup(json_str: str) -> str:
    """基础清理：处理常见的不规范 JSON 格式"""
    json_str = json_str.strip()
    # 修复中文引号或智能引号
    json_str = json_str.replace('“', '"').replace('”', '"')
    json_str = json_str.replace("‘", "'").replace("’", "'")
    # 修复多余的尾随逗号 (如 {"a": 1,} -> {"a": 1})
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    return json_str

def progressive_quote_fix(json_str: str) -> str:
    """进阶清理：处理转义字符和引号问题"""
    # 仅转义引号前未转义的反斜杠
    json_str = re.sub(r'(?<!\\)\\(?=")', r"\\\\", json_str)

    def fix_string_content(match):
        content = match.group(1)
        # 修复字符串值中未转义的反斜杠 (例如 \alpha -> \\alpha)
        content = re.sub(r"\\(?=[a-zA-Z])", r"\\\\", content)
        return f'"{content}"'

    json_str = re.sub(r'"([^"]*(?:\\.[^"]*)*)"', fix_string_content, json_str)
    return json_str

def extract_all_json_candidates(response: str) -> list:
    """从模型长文本回复中提取所有可能的 JSON 候选字符串"""
    candidates = []

    # 预处理：移除推理模型（如 DeepSeek-R1, Qwen-math）产生的思考过程标签
    cleaned_response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL | re.IGNORECASE)
    cleaned_response = re.sub(r"<thinking>.*?</thinking>", "", cleaned_response, flags=re.DOTALL | re.IGNORECASE)

    # 策略 1：匹配 Markdown 代码块中的 JSON (```json ... ```)
    json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_response, re.DOTALL)
    candidates.extend(json_blocks)

    # 策略 2：利用大括号平衡匹配提取纯 JSON 对象
    brace_count = 0
    start_pos = -1
    for i, char in enumerate(cleaned_response):
        if char == "{":
            if brace_count == 0:
                start_pos = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start_pos != -1:
                candidates.append(cleaned_response[start_pos : i + 1])

    # 策略 3：简单的正则兜底提取
    simple_match = re.search(r"\{.*\}", cleaned_response, re.DOTALL)
    if simple_match:
        candidates.append(simple_match.group(0))

    return candidates

def extract_fields_with_regex(response: str) -> dict:
    """终极兜底：当 JSON 完全损坏时，用正则强行提取关键字段"""
    logger.warning("JSON 解析完全失败，正在使用正则表达式回退提取字段")

    # 提取 detailed_description
    desc_match = re.search(r'"detailed_description":\s*"([^"]*(?:\\.[^"]*)*)"', response, re.DOTALL)
    description = desc_match.group(1) if desc_match else ""

    # 提取 entity_name
    name_match = re.search(r'"entity_name":\s*"([^"]*(?:\\.[^"]*)*)"', response)
    entity_name = name_match.group(1) if name_match else "unknown_entity"

    # 提取 entity_type
    type_match = re.search(r'"entity_type":\s*"([^"]*(?:\\.[^"]*)*)"', response)
    entity_type = type_match.group(1) if type_match else "unknown"

    # 提取 summary
    summary_match = re.search(r'"summary":\s*"([^"]*(?:\\.[^"]*)*)"', response, re.DOTALL)
    summary = summary_match.group(1) if summary_match else description[:100]

    return {
        "detailed_description": description,
        "entity_info": {
            "entity_name": entity_name,
            "entity_type": entity_type,
            "summary": summary,
        },
    }

def robust_json_parse(response: str) -> dict:
    """
    对外暴露的主函数：高度鲁棒的 JSON 解析器
    能处理包含 Markdown、思考标签、轻微语法错误的 LLM JSON 输出
    """
    candidates = extract_all_json_candidates(response)

    # 尝试 1：直接解析
    for json_candidate in candidates:
        result = try_parse_json(json_candidate)
        if result:
            return result

    # 尝试 2：基础清理后解析
    for json_candidate in candidates:
        cleaned = basic_json_cleanup(json_candidate)
        result = try_parse_json(cleaned)
        if result:
            return result

    # 尝试 3：进阶转义修复后解析
    for json_candidate in candidates:
        fixed = progressive_quote_fix(json_candidate)
        result = try_parse_json(fixed)
        if result:
            return result

    # 尝试 4：所有 JSON 解析手段均失败，正则暴力提取
    return extract_fields_with_regex(response)