from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Tuple
import pypdfium2 as pdfium
from mineru.utils.pdf_image_tools import pdf_page_to_image
from mineru.utils.enum_class import ImageType
import multiprocessing as mp
import threading
import os 
import tempfile
from loguru import logger

# 设置并行度，太多进程也不好
CONCURRENCY = min(mp.cpu_count()//4, 8)

# 全局进程池管理器
class GlobalProcessPool:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            ctx = mp.get_context('fork')
            max_workers = max(2, CONCURRENCY)  # 增加工作进程数
            self.executor = ProcessPoolExecutor(mp_context=ctx, max_workers=max_workers)
            # self.executor = ctx.ProcessPoolExecutor(max_workers=max_workers)
            self._initialized = True
    
    def get_executor(self):
        return self.executor
    
    def shutdown(self):
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)

# 处理PDF
def render_page_batch(pdf_path:str,page_index: int, pages:int, dpi: int) -> List[Dict]:
    logger.info(f"process: {os.getpid()} is processing from page_index:{page_index} for pages:{pages} dpi:{dpi}")
    pdf_doc = pdfium.PdfDocument(pdf_path)
    all_pages = []
    for i in range(page_index, page_index + pages):
        page = pdf_doc[i]
        all_pages.append(pdf_page_to_image(page, dpi=dpi, image_type=ImageType.PIL))
    pdf_doc.close()  # 确保关闭文档
    return all_pages

# 把pdf放入临时文件中
def write_temp_pdf(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(pdf_bytes)
        pdf_path = tmp_file.name
    return pdf_path

# 使用全局进程池
def load_images_from_pdf(pdf_bytes, start_page_id=0, end_page_id=None, dpi=200, image_type = ImageType.PIL):
    pdf_path = write_temp_pdf(pdf_bytes)
    pdf_doc = pdfium.PdfDocument(pdf_path)
    total_pages = len(pdf_doc)
    try:
        end_page_id = end_page_id if end_page_id is not None else total_pages - 1
        end_page_id = min(end_page_id, total_pages - 1)
        step = max(1, (end_page_id - start_page_id + 1) // CONCURRENCY)
        task_indices = []
        for i in range(start_page_id, end_page_id + 1, step):
            last_page = min(i + step, end_page_id + 1)
            if not last_page > i:
                raise ValueError(f"last_page({last_page}) must be greater than i({i})")
            task_indices.append((i, last_page - i))
        
        executor = GlobalProcessPool().get_executor()
        futures = [(i, executor.submit(render_page_batch, pdf_path, i, pages, dpi)) for i, pages in task_indices]
        results = []
        for start_page, future in futures:
            results.append((start_page, future.result()))

        results.sort(key=lambda x: x[0])  # 按页号排序
        images_list = []
        for start_page, batch in results:
            images_list.extend(batch)
        return images_list, pdf_doc
    except Exception as e:
        raise e
    finally:
        os.remove(pdf_path) # 释放文件资源
