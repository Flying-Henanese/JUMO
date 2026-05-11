import os
import json
from mineru.utils.enum_class import MakeMode
from mineru.backend.hybrid.hybrid_analyze import doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make


def _process_pdf(file_name,pdf_bytes, output_path,):
    server_url = os.getenv("VLLM_SERVER_URL", "http://vllm:8000/v1")
    # 注意：OCR语言通过函数参数传递，不是环境变量
    middle_json, infer_result, _ = doc_analyze(
        pdf_bytes,
        image_writer=None,
        backend="http-client",
        server_url=server_url,
        language="zh-CN"
    )
    # markdown 内容
    pdf_info = middle_json["pdf_info"]
    md_str = vlm_union_make(pdf_info, MakeMode.MM_MD)  # ★
    
    clean_md = md_str.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
    with open(os.path.join(output_path, f"{file_name}.md"), "w", encoding="utf-8") as f:
        f.write(clean_md)

if __name__ == "__main__":
    import sys
    
    # 从命令行参数获取输入目录和输出目录，或使用默认值
    # 默认指向容器内挂载的 /app/data 目录
    input_dir = "/app/data/input"
    output_path = "/app/data/output"
    
    # 确保输出目录存在
    os.makedirs(output_path, exist_ok=True)
    
    if not os.path.exists(input_dir):
        print(f"错误: 输入目录不存在: {input_dir}")
        sys.exit(1)
    
    # 遍历输入目录中的所有 PDF 文件
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    
    print(f"找到 {len(pdf_files)} 个 PDF 文件待处理")
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        file_path = os.path.join(input_dir, pdf_file)
        file_name = os.path.splitext(pdf_file)[0]  # 去掉扩展名
        
        print(f"[{idx}/{len(pdf_files)}] 正在处理: {pdf_file}")
        
        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
            
            _process_pdf(file_name, pdf_bytes, output_path)
            print(f"[{idx}/{len(pdf_files)}] 处理完成: {pdf_file}")
        except Exception as e:
            print(f"[{idx}/{len(pdf_files)}] 处理失败: {pdf_file}, 错误: {e}")
    
    print(f"\n全部处理完成，输出目录: {output_path}")