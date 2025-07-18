import argparse
import os
import subprocess
from pathlib import Path
import torch
import importlib
import dill
import numpy as np

def is_zip_file(path: str) -> bool:
    """判断是否为 zip 格式模型"""
    try:
        out = subprocess.check_output(["file", "-b", path]).decode()
        return "Zip archive data" in out
    except Exception:
        return False

def register_safe_globals_from_checkpoint(input_path: str):
    """自动注册 PyTorch 权重文件中使用的自定义类"""
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
        registered.append(dill._dill._load_type)
        torch.serialization.add_safe_globals(registered)
    except Exception as e:
        print(f"⚠️ 注册 safe globals 失败: {e}")

def convert_to_zip(input_path: str, output_path: str = None, delete_original: bool = False, link_pt: bool = False):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    
    # 已经是 zip 格式就跳过
    if is_zip_file(input_path):
        print(f"✅ 已是 zip 格式，跳过: {input_path}")
        return

    input_path = Path(input_path)
    output_path = Path(output_path or input_path.with_suffix(".zip"))

    try:
        register_safe_globals_from_checkpoint(str(input_path))
        
        with open(input_path, 'rb') as f:
            checkpoint = torch.load(f, map_location="cpu", weights_only=False)

        # 可选转换 numpy.float64 → tensor
        if isinstance(checkpoint, dict):
            for key, val in checkpoint.items():
                if isinstance(val, np.floating):
                    checkpoint[key] = torch.tensor(val)
                    print(f"🔧 已转换 {key} 为 torch.tensor")

        # 用 zip 格式保存
        torch.save(checkpoint, output_path, _use_new_zipfile_serialization=True)

        if not is_zip_file(output_path):
            raise RuntimeError(f"{output_path} 保存失败，格式仍非 zip！")

        print(f"✅ 转换完成: {input_path} → {output_path}")

        # 创建软链接 .pt → .zip
        if link_pt:
            if input_path.exists():
                input_path.unlink()
            input_path.symlink_to(output_path.name)
            print(f"🔗 已创建软链接: {input_path} → {output_path.name}")
        
        # 删除原始文件（不删软链接）
        if delete_original and not link_pt and input_path.exists():
            input_path.unlink()
            print(f"🗑️ 已删除原始文件: {input_path}")

    except Exception as e:
        print(f"❌ 转换失败 {input_path}: {e}")

def find_and_convert_pt_files(directory: str, delete_original: bool = False, link_pt: bool = False):
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"目录不存在: {directory}")
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".pt"):
                pt_path = os.path.join(root, file)
                convert_to_zip(pt_path, delete_original=delete_original, link_pt=link_pt)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="目录路径")
    parser.add_argument("--delete", action="store_true", help="转换后删除原文件")
    parser.add_argument("--link-pt", action="store_true", help="转换后为 zip 文件创建 .pt 软链接")
    args = parser.parse_args()

    find_and_convert_pt_files(args.dir, delete_original=args.delete, link_pt=args.link_pt)
    print("🎉 全部转换完成！")