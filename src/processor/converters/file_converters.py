"""
File Format Converters
======================

This module provides utility functions for converting office documents to intermediate formats
using LibreOffice. It is primarily used to normalize input files (e.g., .doc to .docx, or Office to PDF)
before further processing.

Dependencies:
-------------
-   **LibreOffice (`soffice`)**: Must be installed and available in the system PATH.
"""
import subprocess
import tempfile
from pathlib import Path

def office_bytes_to_pdf_bytes(word_bytes: bytes, suffix:str=".docx") -> bytes:
    """将Word文件字节流转换为PDF字节流。
       启动一个子进程，调用libreoffice进行转换
    参数:
        word_bytes: Word文件的字节流。
        suffix: 文件后缀（.docx或.doc），用于保存临时文件。

    返回:
        PDF文件的字节流。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        input_path = tmpdir_path / f"input{suffix}"
        output_path = tmpdir_path / "input.pdf"

        # 写入临时Word文件
        input_path.write_bytes(word_bytes)

        # 执行LibreOffice命令转换为PDF
        subprocess.run([
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            str(input_path),
            "--outdir", str(tmpdir_path)
        ], check=True)

        # 读取并返回PDF字节流
        return output_path.read_bytes()


def office_bytes_to_docx_bytes(word_bytes: bytes, suffix: str = ".doc") -> bytes:
    """将旧版 Word (.doc) 字节流转换为 .docx 字节流，便于后续 markdown 处理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        input_path = tmpdir_path / f"input{suffix}"
        output_path = tmpdir_path / "input.docx"
        input_path.write_bytes(word_bytes)
        subprocess.run([
            "soffice",
            "--headless",
            "--convert-to", "docx",
            str(input_path),
            "--outdir", str(tmpdir_path)
        ], check=True)
        return output_path.read_bytes()