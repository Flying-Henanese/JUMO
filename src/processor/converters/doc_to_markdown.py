from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, DocItemLabel
import os
import re
from docling_core.types.doc import DoclingDocument
from startup import minio_tool
from PIL import Image
# 配置
MAX_CHUNK_SIZE = 500  # 每段最大字符数


def doc_to_markdown(input_data : str,task_id:str,bucket:str) -> str:
    """
    将 Word 文档（.docx）转换为 Markdown，支持文件路径和字节流输入，保留表格、图片和标题层级。
    :param input_data: 文件路径（str）或字节流（bytes）
    :return: 转换后的 Markdown 文本
    """
    converter = DocumentConverter()
    result = converter.convert(input_data)
    
    md_content = remove_toc(result.document).export_to_markdown()
    md_content = insert_images_to_markdown(result.document,md_content,task_id,bucket)
    # 最后使用process_markdown进行切分
    return md_content


def remove_toc(doc: DoclingDocument) -> DoclingDocument:
    """
    从 DoclingDocument 中删除目录（TOC）相关的 items。
    通过两类信号识别：
      1) 类名/类型名包含 toc/table_of_contents
      2) 文本特征：'目录'/'contents' 标题、点线+页码、纯页码行
    """

    def is_toc_like_item(item) -> bool:
        # 1) 根据类名/类型名判断
        cls = item.__class__.__name__.lower()
        if cls in {"tocentry", "tableofcontents", "table_of_contents", "toc"}:
            return True

        # 2) 文本特征判断（兜底）
        text = getattr(item, "text", "") or ""
        text = text.strip()
        if not text:
            return False

        if (
            re.fullmatch(r"(目录|contents)", text, flags=re.I)             # “目录” / “contents”
            or re.search(r"\.{2,}\s*\d+$", text)                           # …… 12
            or re.fullmatch(r"\d+", text)                                  # 纯页码
        ):
            return True

        return False

    # --- 遍历 item 树并收集待删除项 ---
    # iterate_items() 的返回值形式可能是 item 或 (stack, item)，两种都兼容
    items_to_delete = []
    for it in doc.iterate_items():
        item = it[0] if isinstance(it, (tuple, list)) else it
        try:
            if is_toc_like_item(item):
                items_to_delete.append(item)
        except Exception:
            # 某些 item 没有 text 等属性，直接跳过即可
            continue

    # --- 执行删除 ---
    if items_to_delete:
        doc.delete_items(items_to_delete)

    return doc


def remove_toc_old(doc: DoclingDocument) -> DoclingDocument:
    """
    删除 DoclingDocument 中的目录信息，仅保留正文。
    """
    def is_toc_element(elem) -> bool:
        text = getattr(elem, "text", "").strip()

        # 1. 如果 element_type 明确标识是目录项
        if getattr(elem, "element_type", "").lower() in {"tocentry", "table_of_contents"}:
            return True

        # 2. 文本特征判断（兜底）
        # - 以 "目录" 或 "contents" 开头
        # - 大量省略号/点线连接页码
        # - 纯页码行
        if (
            re.match(r"^(目录|contents)$", text, flags=re.I)
            or re.search(r"\.{2,}\s*\d+$", text)  # 点线 + 页码
            or re.fullmatch(r"\d+", text)         # 纯数字
        ):
            return True

        return False

    # 过滤 elements
    # Check if the document uses 'items' or 'content' instead of 'elements'
    if hasattr(doc, 'items'):
        filtered_elements = [elem for elem in doc.items if not is_toc_element(elem)]
    elif hasattr(doc, 'content'):
        filtered_elements = [elem for elem in doc.content if not is_toc_element(elem)]
    else:
        raise AttributeError("DoclingDocument has no accessible elements attribute. Available attributes: " + str(dir(doc)))

    # 返回一个新的 DoclingDocument 对象（保留原元数据）
    new_doc = DoclingDocument(
        metadata=doc.metadata,
        elements=filtered_elements
    )

    return new_doc


def insert_images_to_markdown(doc:DoclingDocument,markdown_content:str,task_id:str,bucket:str) -> str:
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
        if node.model_dump().get("label") == DocItemLabel.PICTURE:
            # 获取图片引用
            image_ref = node.model_dump().get("image")
            if image_ref:
                # 获取图片数据
                image:Image.Image = node.get_image(doc)
                if image:
                    # 生成图片文件名
                    image_filename = f"image_{image_counter}.png"
                    image_path = os.path.join(task_id, image_filename)
                    image_counter += 1
                    # 上传图片到minio
                    minio_tool.upload_file_by_bytes(
                        object_name=image_path,
                        bucket_name=bucket,
                        file_bytes=image.tobytes(),
                        content_type=f"image/{image_filename.split('.')[-1]}")
                    # 替换 Markdown 内容中的占位符
                    placeholder = "<!-- image -->"
                    markdown_content = markdown_content.replace(placeholder, f"![]({image_path})", 1)
    return markdown_content


# 示例用法
if __name__ == "__main__":
    md1 = doc_to_markdown("a.docx","a")
    print("Markdown (from path):\n", md1)