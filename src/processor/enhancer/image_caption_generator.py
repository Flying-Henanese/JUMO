import base64
import json
from utils.llm_response_parser import robust_json_parse
from processor.image_processing.image_enhancer import PROMPTS
from processor.enhancer.multimodal_enhancer import ContextExtractor


async def generate_enhanced_caption_from_bytes(
    image_bytes: bytes,
    vlm_model_func,
    context_extractor: ContextExtractor = None,
    item_info: dict = None,
    image_name: str = "uploaded_image"
):
    """
    直接从图片字节流生成增强描述
    :param image_bytes: 图片的原始字节数据 (bytes)
    :param vlm_model_func: VLM 调用函数
    :param context_extractor: 上下文提取器
    :param item_info: 位置信息（用于提取上下文）
    :param image_name: 给图片起个名字，用于填充 prompt 中的 entity_name
    """

    # 1. 字节流转 Base64 (这是 VLM 接口通常要求的格式)
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # 2. 提取上下文 (Context)
    # 如果你在处理一个文档流，item_info 应该包含当前图片在流中的 index 或 page_idx
    context = ""
    if context_extractor and item_info:
        context = context_extractor.extract_context(
            content_source=None,
            current_item_info=item_info
        )

    # 3. 准备提示词变量映射
    # 注意：因为是字节流，image_path 传一个描述性字符串即可，或者传 None
    prompt_vars = {
        "entity_name": image_name,
        "image_path": "memory_stream",
        "captions": item_info.get("original_caption", "None") if item_info else "None",
        "footnotes": "None",
        "context": context
    }

    # 4. 根据是否有上下文选择 Template
    if context:
        user_prompt = PROMPTS["vision_prompt_with_context"].format(**prompt_vars)
    else:
        # 如果没有 context，手动移除模板中可能需要的变量（或者使用基础模板）
        user_prompt = PROMPTS["vision_prompt"].format(
            entity_name=prompt_vars["entity_name"],
            image_path=prompt_vars["image_path"],
            captions=prompt_vars["captions"],
            footnotes=prompt_vars["footnotes"]
        )

    # 5. 调用模型
    system_prompt = PROMPTS["IMAGE_ANALYSIS_SYSTEM"]

    try:
        raw_response = await vlm_model_func(
            prompt=user_prompt,
            system_prompt=system_prompt,
            image_data=image_base64
        )

        # 6. 鲁棒解析 JSON
        # 这一步非常重要，因为模型经常会多嘴或者加 think 标签
        parsed_result = robust_json_parse(raw_response)

        return {
            "success": True,
            "enhanced_caption": parsed_result.get("detailed_description", ""),
            "entity_name": parsed_result.get("entity_info", {}).get("entity_name", image_name),
            "summary": parsed_result.get("entity_info", {}).get("summary", ""),
            "raw": parsed_result
        }

    except Exception as e:
        print(f"VLM processing failed: {e}")
        return {"success": False, "error": str(e)}
