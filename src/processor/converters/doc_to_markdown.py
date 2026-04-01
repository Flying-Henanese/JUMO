"""
Word to Markdown Converter
==========================

This module utilizes the `docling` library to convert Word documents (.docx) into Markdown format.
It includes post-processing steps to clean up the output, such as removing the Table of Contents (TOC),
extracting and uploading images to MinIO, and handling table/caption formatting.

Key Functions:
--------------
-   `doc_to_markdown`: The main entry point for conversion.
-   `_remove_toc`: Heuristic-based removal of TOC sections.
-   `_insert_images_to_markdown`: Handles image extraction and URL replacement.
"""
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, DocItemLabel
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PaginatedPipelineOptions
from docling.document_converter import WordFormatOption
import os
import re
import io
from startup import minio_tool
from PIL import Image
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.types.doc.document import DOCUMENT_TOKENS_EXPORT_LABELS

"""
转换word文档为markdown格式(基于docling实现)
"""

def doc_to_markdown(
    input_data : str,
    task_id:str = "no_specific_task_id",
    bucket:str = None,
    oss_info: dict = None,
    return_images: bool = False
    ):
    """
    Converts a Word document (.docx) to Markdown, preserving tables, images, and hierarchy.

    Args:
        input_data (str): Path to the input .docx file.
        task_id (str, optional): Task ID for organizing extracted images in storage. Defaults to "no_specific_task_id".
        bucket (str, optional): Name of the S3/MinIO bucket to upload extracted images.

    Returns:
        str: The converted Markdown content.
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
    processed_doc = result.document
    # 处理caption与表格/图片的合并,失败了，以后再完善吧
    # processed_doc = _merge_captions_with_content(processed_doc)
    md_serializer = MarkdownDocSerializer(doc=processed_doc)
    allowed_labels = {l for l in DOCUMENT_TOKENS_EXPORT_LABELS if l != DocItemLabel.DOCUMENT_INDEX}
    md_content = md_serializer.serialize(labels=allowed_labels).text
    # 把文档中的图片提取出来
    # 1. 首先放入minio中
    # 2. 把所有图片的url替换为minio中的url,用于后续前端应用读取图片进行渲染
    md_content, image_paths = _insert_images_to_markdown(processed_doc, md_content, task_id, bucket, oss_info)
    if return_images:
        return md_content, image_paths
    return md_content


def _remove_toc(doc: DoclingDocument) -> DoclingDocument:
    """
    Removes Table of Contents (TOC) items from the DoclingDocument.

    This function identifies TOC items using two strategies:
    1.  **Class/Type Name**: Checks if the item's class name contains "toc" or "tableofcontents".
    2.  **Text Heuristics**: Checks for patterns like "Table of Contents", dot leaders with page numbers,
        or standalone page numbers (Roman or Arabic).

    Args:
        doc (DoclingDocument): The parsed document object.

    Returns:
        DoclingDocument: The document with TOC items removed.
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
        doc.delete_items(node_items=items_to_delete)

    return doc


def _insert_images_to_markdown(
    doc:DoclingDocument,
    markdown_content:str,
    task_id:str = "no_specific_task_id",
    bucket:str = None,
    oss_info: dict = None
    ):
    """
    Extracts images from the document, uploads them to object storage, and updates Markdown references.

    It iterates through the document items to find pictures, extracts the image data,
    uploads it to the specified MinIO bucket, and replaces the `<!-- image -->` placeholder
    in the Markdown content with the actual image URL.

    Args:
        doc (DoclingDocument): The parsed document object containing image data.
        markdown_content (str): The raw Markdown content with image placeholders.
        task_id (str): Task ID used for naming the image path in storage.
        bucket (str): The target bucket name for upload.

    Returns:
        str: The Markdown content with valid image links.
    """
    image_counter = 0
    image_paths = []
    for it in doc.iterate_items():
        node = it[0] if isinstance(it, (tuple, list)) else it
        node_data = node.model_dump() if hasattr(node, "model_dump") else {}
        label = node_data.get("label")
        label_str = str(label).lower()
        if label == DocItemLabel.PICTURE or label_str in {"picture", "docitemlabel.picture"}:
            image_ref = node_data.get("image")
            if image_ref:
                image: Image.Image = node.get_image(doc)
                if image:
                    image_filename = f"image_{image_counter}.png"
                    image_path = os.path.join(task_id, "images", image_filename)
                    image_counter += 1
                    if not bucket:
                        continue
                    image_bytes_buffer = io.BytesIO()
                    image.save(image_bytes_buffer, format="PNG")
                    minio_tool.upload_file_by_bytes(
                        object_name=image_path,
                        bucket_name=bucket,
                        file_bytes=image_bytes_buffer.getvalue(),
                        content_type="image/png",
                        oss_info=oss_info
                    )
                    image_paths.append(image_path)
                    placeholder = "<!-- image -->"
                    if placeholder in markdown_content:
                        markdown_content = markdown_content.replace(placeholder, f"![]({image_path})", 1)
                    else:
                        markdown_content = f"{markdown_content}\n\n![]({image_path})"
    return markdown_content, image_paths

def _merge_captions_with_content(doc: DoclingDocument) -> DoclingDocument:
    """
    Merges caption elements with their corresponding table or picture elements.

    This function iterates through the document items and attempts to link orphan captions
    with adjacent tables or images. It looks both backwards and forwards to find the nearest
    matching content element and combines the text.

    Args:
        doc (DoclingDocument): The parsed document object.

    Returns:
        DoclingDocument: The document with captions merged into content items.
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
        doc.delete_items(node_items=items_to_delete)
    
    return doc