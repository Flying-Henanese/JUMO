import subprocess
import tempfile
from pathlib import Path

import tempfile
import subprocess
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

