import pandas as pd

from utils.logging import AppLogger

logger = AppLogger.get_logger(__name__)


def excel_to_markdown(
    excel_content, key_columns=[1], header_row_number=1, file_name="表格",is_csv = False
) -> list:
    """
    将Excel文件内容转换为Markdown格式的列表

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
        # ========== 参数校验 ==========
        if not isinstance(key_columns, list):
            raise TypeError("key_columns 必须是一个列表")
        if len(key_columns) > 3:
            raise ValueError("最多只能指定3个关键列")
        if len(key_columns) == 0:
            raise ValueError("至少需要指定1个关键列")

        # 读取Excel文件
        if is_csv:
            df = pd.read_csv(excel_content,header=None)
        else:
            df = pd.read_excel(
                excel_content, engine="openpyxl", header=None  # 不指定标题行，因为会把这一行的列名作为索引
            )

        # 校验关键列是否存在
        invalid_columns = []
        for col in key_columns:
            if isinstance(col, str) and col not in df.columns:
                invalid_columns.append(f"列名 '{col}'")
            elif isinstance(col, int) and col >= len(df.columns):
                invalid_columns.append(f"列索引 {col}")

        if invalid_columns:
            raise ValueError(f"无效的关键列: {', '.join(invalid_columns)}")

        # ========== 核心转换逻辑 ==========
        base_name = file_name
        md_content = []
        # 从标题行下面开始遍历所有数据行
        # title_row 即为读取到的标题行
        titles_row = df.iloc[header_row_number]
        for index, row in df.iterrows():
            if index <= header_row_number:
                continue
            key_values = []
            for col in key_columns:
                value = row[col]
                key_values.append(str(value) if not pd.isna(value) else "NULL")

            combined_keys = " | ".join(key_values)

            # 构建标题（限制在80字符内）
            title = f"# {base_name} | {combined_keys} | 行{index+1}"
            if len(title) > 80:  # 防止标题过长,如果太长则只保留文件名、行号以及首个关键列
                title = f"# {base_name} | 行{index+1} | {key_values[0]}..."

            md_content.append(title + "\n")

            # 添加字段详情（实际内容）
            for field in df.columns:
                value = row[field]
                display_value = "NULL" if pd.isna(value) else str(value)
                # 取标题行的第field列作为这一个小段的标题，标题使用- ****进行加粗处理
                md_content.append(f"- **{titles_row[field]}**: {display_value}\n")

            md_content.append("\n")  # 行间分隔
            md_content.append("----------") # 与知识库之间约定的分隔符
            md_content.append("\n\n") # 再添加一个换行

        # region
        # # ========== 文件输出 ==========
        # os.makedirs(output_dir, exist_ok=True)
        # output_path = os.path.join(output_dir, f"{base_name}.md")

        # with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        #     f.writelines(md_content)
        # endregion

        logger.info("转换成功!")
        return md_content
    except Exception as e:
        logger.error(f"处理失败: {type(e).__name__} - {str(e)}")
        raise


# region
# if __name__ == "__main__":
#     # 使用示例
#     excel_path = r".\test.xlsx"
#     output_dir = r".\output"
#     print(excel_to_markdown(excel_path,output_path= output_dir))
# endregion
