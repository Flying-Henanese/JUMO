#!/usr/bin/env python3
# convert_pth_to_zip_npu.py

import torch_npu  # 提前导入，避免设备兼容问题
import torch
import argparse
import os
import tempfile

def is_zipfile_format(path: str) -> bool:
    """判断是否为 zip 序列化格式"""
    try:
        out = os.popen(f"file -b {path}").read()
        return "Zip archive data" in out
    except Exception:
        return False

def convert_to_zip_format(file_path: str):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"找不到模型文件: {file_path}")
    
    if is_zipfile_format(file_path):
        print(f"✅ 模型已是 zip 格式: {file_path}")
        return

    print(f"➡️ 正在转换为 zip 格式: {file_path}")

    # 加载旧格式模型
    ckpt = torch.load(file_path, map_location="cpu")

    # 临时路径保存 zip 格式
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pth") as tmp:
        tmp_path = tmp.name
    torch.save(ckpt, tmp_path, _use_new_zipfile_serialization=True)

    # 覆盖原始模型文件
    os.replace(tmp_path, file_path)
    print(f"✅ 已覆盖保存为 zip 格式: {file_path}")

def verify_load_on_npu(file_path: str):
    try:
        print(f"🧪 正在尝试在 NPU 上加载: {file_path}")
        model_data = torch.load(file_path, map_location="npu:0")
        print("🎉 成功在 NPU 上加载模型！")
    except Exception as e:
        print(f"❌ 无法在 NPU 上加载模型: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pth_file", help="待转换的 .pth 模型文件路径")
    args = parser.parse_args()

    convert_to_zip_format(args.pth_file)
    verify_load_on_npu(args.pth_file)