from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, DocItemLabel
import os
import re
from docling_core.types.doc import DoclingDocument
from startup import minio_tool
from PIL import Image

"""
转换word文档为markdown格式(基于docling实现)
"""

def doc_to_markdown(input_data : str,task_id:str,bucket:str) -> str:
    """
    将 Word 文档（.docx）转换为 Markdown，支持文件路径输入，保留表格、图片和标题层级。
    :param input_data: 文件路径（str）
    :return: 转换后的 Markdown 文本
    """
    # 生成一个文档转换器
    converter = DocumentConverter()
    # 转换文档为 DoclingDocument对象
    result = converter.convert(input_data)
    # 对result.document进行处理,去除目录信息
    # 然后输出为markdown格式
    md_content = remove_toc(result.document).export_to_markdown()
    # 把文档中的图片提取出来
    # 1. 首先放入minio中
    # 2. 把所有图片的url替换为minio中的url,用于后续前端应用读取图片进行渲染
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
                    minio_tool.upload_file_by_bytes(
                        object_name=image_path,
                        bucket_name=bucket,
                        file_bytes=image.tobytes(),
                        content_type=f"image/{image_filename.split('.')[-1]}")
                    # 使用实际存储在OSS中的图片地址替换 Markdown 内容中的占位符
                    placeholder = "<!-- image -->"
                    markdown_content = markdown_content.replace(placeholder, f"![]({image_path})", 1)
    return markdown_content

# region
# 示例用法
# if __name__ == "__main__":
#     md1 = doc_to_markdown("a.docx","a")
#     print("Markdown (from path):\n", md1)
# endregion