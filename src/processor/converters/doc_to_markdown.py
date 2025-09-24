from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PaginatedPipelineOptions
from docling.document_converter import WordFormatOption
import os
import re
from startup import minio_tool
from PIL import Image

"""
转换word文档为markdown格式(基于docling实现)
"""

def doc_to_markdown(
    input_data : str,
    task_id:str = "no_specific_task_id",
    bucket:str = None
    ) -> str:
    """
    将 Word 文档（.docx）转换为 Markdown，支持文件路径输入，保留表格、图片和标题层级。
    :param input_data: 文件路径（str）
    :return: 转换后的 Markdown 文本
    """
    # 配置DOCX管道选项以正确处理表格结构
    docx_pipeline_options = PaginatedPipelineOptions()
    
    # 配置DOCX管道选项以正确处理文档分页结构
    converter = DocumentConverter(
        format_options={
            InputFormat.DOCX: WordFormatOption(pipeline_options=docx_pipeline_options),
        }
    )
    # 转换文档为 DoclingDocument对象
    result = converter.convert(input_data)
    # 对result.document进行处理,去除目录信息
    # 然后输出为markdown格式
    processed_doc = _remove_toc(result.document)
    # 处理caption与表格/图片的合并,失败了，以后再完善吧
    # processed_doc = _merge_captions_with_content(processed_doc)
    md_content = processed_doc.export_to_markdown()
    # 把文档中的图片提取出来
    # 1. 首先放入minio中
    # 2. 把所有图片的url替换为minio中的url,用于后续前端应用读取图片进行渲染
    md_content = _insert_images_to_markdown(processed_doc,md_content,task_id,bucket)
    # 最后使用process_markdown进行切分
    return md_content


def _remove_toc(doc: DoclingDocument) -> DoclingDocument:
    """
    从 DoclingDocument 中删除目录（TOC）相关的 items。
    通过两类信号识别：
      1) 类名/类型名包含 toc/table_of_contents
      2) 文本特征：'目录'/'contents' 标题、点线+页码、纯页码行
    """

    def is_toc_like_item(item) -> bool:
        # 1) 根据条目类名/类型名判断
        cls = item.__class__.__name__.lower()
        # 如果这个条目是目录相关的内容，则返回True
        if cls in {"tocentry", "tableofcontents", "table_of_contents", "toc"}:
            return True

        # 2) 文本特征判断（兜底）
        # 获取这个条目的文本信息，如果通过getattr得到的是None，那么就返回空字符串
        text = getattr(item, "text", "") or ""
        text = text.strip() # 去掉文本首尾的空格
        if not text:  # 如果文本为空，那么就返回False
            return False

        if (
                # "目录" 或 "Table of Contents"
                re.fullmatch(r"(目录|table of contents)", text, flags=re.I)
                # 目录项：标题 + 省略号 + 页码
                or re.fullmatch(r".+\.{2,}\s*\d+$", text)
                # 纯页码（阿拉伯或罗马数字），并且长度限制
                or re.fullmatch(r"[ivxlcdmIVXLCDM\d]{1,5}", text) 
        ):
            return True

        return False

    # --- 遍历 item 树并收集待删除项 ---
    # iterate_items() 的返回值形式可能是 item 或 (stack, item)，两种都兼容
    items_to_delete = []
    for it in doc.iterate_items():# 这里除了返回item，还会有一个len(stack)，就是文档树的深度
        # 提取item 
        # 因为item的类型可能集合，也有可能是单个对象
        # 所以对于集合就提取第一个元素，对于单个对象就直接使用
        item = it[0] if isinstance(it, (tuple, list)) else it
        try:
            # 如果这个条目是目录相关的内容，那么就添加到删除列表中
            if is_toc_like_item(item):
                items_to_delete.append(item)
        except Exception:
            # 某些 item 没有 text 等属性，直接跳过即可
            continue

    # --- 执行删除 ---
    if items_to_delete:
        doc.delete_items(items_to_delete)

    return doc


def _insert_images_to_markdown(
    doc:DoclingDocument,
    markdown_content:str,
    task_id:str = "no_specific_task_id",
    bucket:str = None
    ) -> str:
    """
    插入文档中的图片到Markdown内容中
    :param doc: DoclingDocument对象
    :param md_content: 原始Markdown内容
    :return: 包含图片的Markdown内容
    """
    image_counter = 0
    # 遍历文档中的图片
    for node,_ in doc.iterate_items():
        # 检查节点标签是否为图片
        # 这里其实就是把node作为pydantic模型进行序列化处理进而转换成一个dict字典
        # 然后检查是否有属性label
        # 使用字典可以避免因为属性不存在而导致的错误
        # 还有一个点就是node是一个docling文档节点，他不一定有label对象
        if node.model_dump().get("label") == DocItemLabel.PICTURE:
            # 获取图片引用
            image_ref = node.model_dump().get("image")
            if image_ref:
                # 获取图片数据
                image:Image.Image = node.get_image(doc) # 可能因为图片依赖文档全局信息，所以把所属的文档对象穿进去获取图片了
                if image:
                    # 生成图片文件名
                    image_filename = f"image_{image_counter}.png"
                    image_path = os.path.join(task_id, image_filename)
                    image_counter += 1
                    # 上传图片到minio
                    if not bucket:
                        continue
                    minio_tool.upload_file_by_bytes(
                        object_name=image_path,
                        bucket_name=bucket,
                        file_bytes=image.tobytes(),
                        content_type=f"image/{image_filename.split('.')[-1]}")
                    # 使用实际存储在OSS中的图片地址替换 Markdown 内容中的占位符
                    placeholder = "<!-- image -->"
                    markdown_content = markdown_content.replace(placeholder, f"![]({image_path})", 1)
    return markdown_content

def _merge_captions_with_content(doc: DoclingDocument) -> DoclingDocument:
    """
    将caption元素与其对应的表格或图片合并，形成带标题的内容块。
    优化版本：基于文档顺序进行单次遍历匹配。
    
    :param doc: DoclingDocument对象
    :return: 处理后的DoclingDocument对象
    """
    items_to_delete = []
    items_list = list(doc.iterate_items())
    
    # 单次遍历，基于位置关系匹配caption与内容
    for i, item in enumerate(items_list):
        node = item[0] if isinstance(item, (tuple, list)) else item
        node_data = node.model_dump()
        label = node_data.get("label")
        
        # 如果当前元素是表格或图片，寻找相邻的caption
        if label in [DocItemLabel.TABLE, DocItemLabel.PICTURE]:
            caption_node = None
            caption_text = ""
            
            # 向前查找caption（caption通常在内容之前）
            for j in range(i-1, max(-1, i-3), -1):  # 最多向前查找2个元素
                if j < 0:
                    break
                prev_item = items_list[j]
                prev_node = prev_item[0] if isinstance(prev_item, (tuple, list)) else prev_item
                prev_label = prev_node.model_dump().get("label")
                
                if prev_label == DocItemLabel.CAPTION:
                    caption_node = prev_node
                    caption_text = getattr(prev_node, 'text', '')
                    break
                elif prev_label in [DocItemLabel.TABLE, DocItemLabel.PICTURE]:
                    # 如果遇到其他内容元素，停止查找
                    break
            
            # 如果前面没找到，向后查找caption（有些caption可能在内容之后）
            if not caption_node:
                for j in range(i+1, min(len(items_list), i+3)):  # 最多向后查找2个元素
                    if j >= len(items_list):
                        break
                    next_item = items_list[j]
                    next_node = next_item[0] if isinstance(next_item, (tuple, list)) else next_item
                    next_label = next_node.model_dump().get("label")
                    
                    if next_label == DocItemLabel.CAPTION:
                        caption_node = next_node
                        caption_text = getattr(next_node, 'text', '')
                        break
                    elif next_label in [DocItemLabel.TABLE, DocItemLabel.PICTURE]:
                        # 如果遇到其他内容元素，停止查找
                        break
            
            # 如果找到了匹配的caption，进行合并
            if caption_node and caption_text:
                print(f"合并caption: {caption_text} 与 内容: {node.model_dump().get('text', '')}")
                try:
                    # 尝试将caption文本添加到内容项中
                    if hasattr(node, 'text'):
                        original_text = getattr(node, 'text', '')
                        combined_text = f"**{caption_text}**\n\n{original_text}"
                        setattr(node, 'text', combined_text)
                    elif hasattr(node, 'caption'):
                        setattr(node, 'caption', caption_text)
                    
                    # 标记caption节点为待删除
                    items_to_delete.append(caption_node)
                    
                except (AttributeError, TypeError):
                    # 如果无法直接修改，跳过
                    pass
    
    # 删除已经合并的caption元素
    if items_to_delete:
        doc.delete_items(items_to_delete)
    
    return doc

# region
# 示例用法
# if __name__ == "__main__":
#     md1 = doc_to_markdown("a.docx","a")
#     print("Markdown (from path):\n", md1)
# endregion