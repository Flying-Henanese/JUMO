import argparse
import os
from pathlib import Path
import torch
import importlib
import dill  # 用于注册 _load_type
import numpy as np  # 别忘了加这个 import

def register_safe_globals_from_checkpoint(input_path: str):
    """自动注册 PyTorch 权重文件中使用的所有自定义全局类/函数"""
    try:
        unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(input_path)
        registered = []
        for path in unsafe:
            try:
                module_name, _, class_name = path.rpartition('.')
                module = importlib.import_module(module_name)
                obj = getattr(module, class_name)
                registered.append(obj)
            except Exception as e:
                print(f"⚠️ 无法导入 {path}: {e}")
        # 加上基本类型
        registered.append(dill._dill._load_type)
        torch.serialization.add_safe_globals(registered)
    except Exception as e:
        print(f"⚠️ 注册安全全局失败: {e}")

def convert_to_zip(input_path: str, output_path: str = None, delete_original: bool = False):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    
    output_path = output_path or str(Path(input_path).with_suffix('.zip'))
    
    try:
        register_safe_globals_from_checkpoint(input_path)
        
        with open(input_path, 'rb') as f:
            checkpoint = torch.load(f, map_location="cpu", weights_only=False)

        # 自动处理 numpy.float64 类型的 my_scalar
        if 'my_scalar' in checkpoint and isinstance(checkpoint['my_scalar'], np.float64):
            checkpoint['my_scalar'] = torch.tensor(checkpoint['my_scalar'])
            print(f"🔧 已转换 my_scalar 为 torch.tensor")

        torch.save(checkpoint, output_path, _use_new_zipfile_serialization=True)
        print(f"✅ 转换完成: {input_path} -> {output_path}")
        
        if delete_original and os.path.exists(output_path):
            os.remove(input_path)
            print(f"🗑️ 已删除原始文件: {input_path}")
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