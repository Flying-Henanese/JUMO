#!/usr/bin/env python3
# safetensors_to_pt_zip.py
"""
把 HuggingFace .safetensors 转为 PyTorch zip-serialization .pt 并在 NPU 上验证加载
"""
import torch_npu  # 必须先导入
import torch
import argparse
from collections import OrderedDict
from safetensors.torch import safe_open

def convert(file_in, file_out):
    print(f"➡️  读取 {file_in}")
    st = OrderedDict()
    with safe_open(file_in, framework="pt", device="cpu") as f:
        for k in f.keys():
            st[k] = f.get_tensor(k)
    print(f"✅ 权重条目: {len(st)}")

    # 保存为 zip 格式的 .pt
    torch.save(st, file_out, _use_new_zipfile_serialization=True)
    print(f"📦 已保存为 zip 格式: {file_out}")

    # CPU 验证
    _ = torch.load(file_out, map_location="cpu")
    print("🔎 torch.load (CPU) 校验通过！")

    # NPU 验证
    try:
        _ = torch.load(file_out, map_location="npu:0")
        print("🚀 torch.load (NPU) 校验通过！")
    except Exception as e:
        print(f"⚠️ NPU 加载失败: {e}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("safetensors")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or args.safetensors.replace(".safetensors", ".pt")
    convert(args.safetensors, out)