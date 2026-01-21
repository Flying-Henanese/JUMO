"""
Excel 转 Markdown 转换器
===========================

本模块将 Excel 文件（.xlsx, .xls）和 CSV 文件转换为 Markdown 友好格式。
旨在准备结构化数据以供知识库（RAG 系统）摄取。

主要功能:
-------------
-   **结构化转换**: 将 Excel 工作表的每一行转换为结构化的 Markdown 块。
-   **关键列**: 允许指定“关键列”以为每条记录生成描述性标题。
-   **格式支持**: 支持标准 Excel 文件（通过 `openpyxl`）和 CSV 文件。
"""
import pandas as pd
from typing import List
from loguru import logger

def excel_to_markdown(
    excel_content, 
    key_columns: List[int] = None, 
    header_row_number=1, 
    file_name="表格",
    is_csv = False
) -> List[str]:
    """
    将Excel文件内容转换为Markdown格式的列表
    最终传递给知识库

    Args:
        excel_content: 可读取的Excel文件内容(文件路径或文件对象)
        key_columns: 用作关键列的列索引/名称列表(1-3个)
        header_row_number: 标题行所在行号(从0开始)
        file_name: 生成Markdown时使用的基础文件名
    Returns:
        list: 包含所有转换后Markdown内容的列表

    Raises:
        TypeError: 参数类型错误
        ValueError: 参数值无效或Excel内容无效
    """
    try:
        if key_columns is None:
            key_columns = [1]

        # ========== 参数校验 ==========
        if not isinstance(key_columns, list):
            raise TypeError("key_columns 必须是一个列表")
        if len(key_columns) > 3:
            raise ValueError("最多只能指定3个关键列")
        if len(key_columns) == 0:
            raise ValueError("至少需要指定1个关键列")
        # 针对没有指定关键列的情况
        # 读取Excel文件，csv和xls族有不同的读取方式
        table : pd.DataFrame = None
        if is_csv:
            table = pd.read_csv(excel_content,header=None)
        else:
            table = pd.read_excel(
                excel_content, engine="openpyxl", header=None  # 不指定标题行，因为会把这一行的列名作为索引
            )

        # 校验关键列是否存在
        # 如果关键列有问题，则放入invalid_columns
        invalid_columns = []
        for col in key_columns:
            if isinstance(col, str) and col not in table.columns:
                invalid_columns.append(f"列名 '{col}'")
            elif isinstance(col, int) and col >= len(table.columns):
                invalid_columns.append(f"列索引 {col}")

        if invalid_columns:
            # 对于无效的关键列，提示用户
            raise ValueError(f"无效的关键列: {', '.join(invalid_columns)}")

        # ========== 核心转换逻辑 ==========
        base_name = file_name
        md_content = [] #
        # 从标题行下面开始遍历所有数据行
        # title_row 即为读取到的标题行，标题行用header_row_number指定
        titles_row = table.iloc[header_row_number]
        # 遍历所有数据行    
        for index, row in table.iterrows():
            # 跳过标题行
            if index <= header_row_number:
                continue
            # 取关键列上的值,用于后续的标题增强
            key_values = [
                str(row[col]) if not pd.isna(row[col]) else "NULL"
                for col in key_columns
            ]

            
            # 合并关键列值，用于后续的标题增强
            combined_keys = " | ".join(key_values)

            # 构建标题（限制在50字符内）
            # 标题的组成结构为：文件名 | 关键列值 | 行号
            title = f"# {base_name} | {combined_keys} | 行{index+1}"[:50]

            # 把标题信息添加到markdown内容中
            md_content.append(title + "\n")

            # 添加字段详情（实际内容）
            for field in table.columns:
                value = row[field]
                display_value = "NULL" if pd.isna(value) else str(value)
                # 取标题行的第field列作为这一个小段的标题，标题使用- ****进行加粗处理
                md_content.append(f"- **{titles_row[field]}**: {display_value}\n")

            md_content.append("\n")  # 行间分隔
            md_content.append("----------") # 与知识库之间约定的不同记录间的分隔符
            md_content.append("\n\n") # 再添加一个换行

        logger.info("转换成功!")
        return md_content
    except Exception as e:
        logger.error(f"处理失败: {type(e).__name__} - {str(e)}")
        raise
