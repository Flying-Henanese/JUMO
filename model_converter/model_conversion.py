#!/usr/bin/env python3
"""
统一转换并验证模型可在 Ascend NPU 上加载：
- .pt/.pth → zip-serialization（原地转换）；
- .safetensors → zip-serialization .pt；
- .onnx → ATC 转换为 .om，可设置 input_name、input_shape。
所有模型处理后均验证可在 NPU 上加载。
用法示例：
  python convert_all_to_npu_ready.py --path模型目录 \
    --soc Ascend310 \
    --onnx-input-name images \
    --onnx-input-shape 1,3,640,640
"""
import argparse, os, subprocess, tempfile, importlib, dill
from pathlib import Path
from collections import OrderedDict

import torch_npu
import torch
from safetensors.torch import safe_open
import acl  # 或者使用 onnxruntime

def is_zipfile(path: str) -> bool:
    try:
        return "Zip archive data" in subprocess.check_output(["file", "-b", path]).decode()
    except:
        return False

def add_safe_globals(pt_path: str):
    try:
        unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(pt_path)
        torch.serialization.add_safe_globals([
            getattr(importlib.import_module(m), c)
            for fq in unsafe
            for m, _, c in [fq.rpartition('.')]
            if m and c] + [dill._dill._load_type])
    except:
        pass

def convert_pt_pth(path: Path):
    add_safe_globals(str(path))
    ckpt = torch.load(path, map_location="cpu")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix)
    torch.save(ckpt, tmp.name, _use_new_zipfile_serialization=True)
    tmp.close()
    if not is_zipfile(tmp.name):
        os.unlink(tmp.name)
        raise RuntimeError("转换后仍非 zip 格式")
    os.replace(tmp.name, path)

def convert_safetensors(path: Path) -> Path:
    out = path.with_suffix(".pt")
    if out.exists():
        return out
    st = OrderedDict()
    with safe_open(path, framework="pt", device="cpu") as f:
        for k in f.keys():
            st[k] = f.get_tensor(k)
    torch.save(st, out, _use_new_zipfile_serialization=True)
    if not is_zipfile(out):
        os.unlink(out)
        raise RuntimeError("safetensors→pt 转换失败")
    return out

def convert_onnx_to_om(path: Path, soc: str, input_name: str, input_shape: str) -> Path:
    om = path.with_suffix(".om")
    if om.exists():
        return om
    cmd = [
        "atc",
        f"--model={path}",
        "--framework=5",
        f"--output={str(om.with_suffix(''))}",
        "--input_format=NCHW",
        f"--input_shape={input_name}:{input_shape}",
        f"--soc_version={soc}"
    ]
    print("ATC command:", " ".join(cmd))
    subprocess.run(" ".join(cmd), shell=True, check=True)
    if not om.exists():
        raise RuntimeError("ATC 转换失败，未产生 .om")
    return om

def validate_npu_torch(path: Path):
    torch.load(path, map_location="npu:0")

def validate_npu_acl(om: Path):
    acl.init()
    try:
        acl.mdl.load_from_file(str(om))
    finally:
        acl.finalize()

def process_file(path: Path, soc: str, iname: str, ishape: str):
    ext = path.suffix.lower()
    try:
        if ext in {".pt", ".pth"}:
            print(f"→ 处理 PyTorch 模型: {path.name}")
            if not is_zipfile(str(path)):
                convert_pt_pth(path)
            validate_npu_torch(path)
            print("✅ NPU 加载 ok")

        elif ext == ".safetensors":
            print(f"→ 处理 safetensors: {path.name}")
            new = convert_safetensors(path)
            validate_npu_torch(new)
            print("✅ safetensors 转换 ok")

        elif ext == ".onnx":
            print(f"→ 处理 ONNX 模型: {path.name}")
            om = convert_onnx_to_om(path, soc, iname, ishape)
            validate_npu_acl(om)
            print("✅ ONNX→OM 转换 ok")

        else:
            print(f"⏭️ 跳过文件: {path.name}")
    except Exception as e:
        print(f"❌ 处理失败 {path.name}: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="模型文件或目录路径")
    ap.add_argument("--soc", default="Ascend310", help="ATC --soc_version")
    ap.add_argument("--onnx-input-name", default="input", help="ONNX 模型 input 名称")
    ap.add_argument("--onnx-input-shape", default="1,3,224,224", help="ONNX input shape: batch,3,H,W")
    args = ap.parse_args()

    p = Path(args.path).expanduser().resolve()
    if p.is_file():
        process_file(p, args.soc, args.onnx_input_name, args.onnx_input_shape)
    elif p.is_dir():
        for f in p.rglob("*"):
            if f.suffix.lower() in {".pt", ".pth", ".safetensors", ".onnx"}:
                process_file(f, args.soc, args.onnx_input_name, args.onnx_input_shape)
    else:
        raise RuntimeError("路径无效")
    print("✅ 全部处理完毕")

if __name__ == "__main__":
    main()