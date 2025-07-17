import argparse
import os
from pathlib import Path
import torch
from torch.serialization import add_safe_globals
import importlib

def get_class_from_string(class_path):
    """通过字符串路径动态导入类"""
    module_path, class_name = class_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

# 动态导入需要允许的类
try:
    YOLOv10DetectionModel = get_class_from_string("doclayout_yolo.nn.tasks.YOLOv10DetectionModel")
    add_safe_globals([YOLOv10DetectionModel])
except Exception as e:
    print(f"⚠️ 安全全局类注册警告: {str(e)}")

def convert_to_zip(input_path: str, output_path: str = None, delete_original: bool = False):
    if not os.path.exists(input_path):
        raise FileNotFoundError(...)
    output_path = output_path or str(Path(input_path).with_suffix('.zip'))
    try:
        # 注册安全全局
        import dill
        from ultralytics.nn.tasks import DetectionModel
        torch.serialization.add_safe_globals([
            dill._dill._load_type,
            DetectionModel
        ])
        with open(input_path, 'rb') as f:
            model_data = torch.load(f, map_location="cpu", weights_only=True)
        torch.save(model_data, output_path, _use_new_zipfile_serialization=True)
        print(...)
        if delete_original and os.path.exists(output_path):
            os.remove(input_path)
            print(...)
    except Exception as e:
        print(f"❌ 转换失败 {input_path}: {str(e)}")

def find_and_convert_pt_files(directory: str, delete_original: bool = False):
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"目录不存在: {directory}")
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".pt"):
                pt_path = os.path.join(root, file)
                convert_to_zip(pt_path, delete_original=delete_original)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="目录路径")
    parser.add_argument("--delete", action="store_true", help="转换后删除原文件")
    args = parser.parse_args()

    find_and_convert_pt_files(args.dir, args.delete)
    print("🎉 操作完成！")