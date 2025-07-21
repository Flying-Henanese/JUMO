#!/usr/bin/env python3
# convert_pt_zip_merge.py
"""
将目录下所有 .pt 模型转为 PyTorch ZIP-serialization：
  --mode zip      ➜ 生成 .zip（可选删 .pt）
  --mode inplace  ➜ 直接覆盖 .pt 为 ZIP 格式
  --mode link     ➜ 生成 .zip 并创建 .pt → .zip 软链接
转换后自动验证 torch.load 能正确读取。
"""
import argparse, os, subprocess, importlib, dill, torch, numpy as np
from pathlib import Path
from shutil import move

def is_zip_file(path: str) -> bool:
    try:
        out = subprocess.check_output(["file", "-b", path]).decode()
        return "Zip archive data" in out
    except Exception:
        return False

def register_safe_globals_in_checkpoint(pt):
    try:
        unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(pt)
        torch.serialization.add_safe_globals(
            [getattr(importlib.import_module(m), c)
             for x in unsafe
             for m, _, c in [x.rpartition('.')]
             if m and c] + [dill._dill._load_type])
    except Exception as e:
        print(f"⚠️ safe_globals 注册失败: {e}")

def save_as_zip(checkpoint, out_path):
    torch.save(checkpoint, out_path, _use_new_zipfile_serialization=True)
    if not is_zip_file(out_path):
        raise RuntimeError("保存后仍不是 zip 格式")

def validate_loadable(pt_path):
    try:
        torch.serialization._is_zipfile(pt_path)  # 额外判定
        _ = torch.load(pt_path, map_location="cpu", weights_only=False)
        return True
    except Exception as e:
        print(f"❌ 验证加载失败: {pt_path}\n{e}")
        return False

def convert_one(pt_path, mode="zip", delete_original=False):
    pt = Path(pt_path)
    if not pt.exists():
        print(f"❌ 文件不存在: {pt}")
        return
    if is_zip_file(pt):
        print(f"✅ 已为 zip 格式: {pt}")
        return

    register_safe_globals_in_checkpoint(str(pt))

    with open(pt, "rb") as f:
        ckpt = torch.load(f, map_location="cpu", weights_only=False)

    # 修正 numpy scalar
    if isinstance(ckpt, dict):
        for k, v in list(ckpt.items()):
            if isinstance(v, np.floating):
                ckpt[k] = torch.tensor(v)

    if mode == "inplace":
        tmp = pt.with_suffix(".pt.tmp")
        save_as_zip(ckpt, tmp)
        if validate_loadable(tmp):
            move(tmp, pt)
            print(f"🎉 覆盖完成: {pt}")
        else:
            tmp.unlink(missing_ok=True)
            print("⚠️ 覆盖回滚")
        return

    # modes zip / link
    zf = pt.with_suffix(".zip")
    save_as_zip(ckpt, zf)
    if not validate_loadable(zf):
        zf.unlink(missing_ok=True)
        return
    print(f"🎉 转换完成: {pt} → {zf}")

    if mode == "link":
        pt.unlink(missing_ok=True)
        pt.symlink_to(zf.name)
        print(f"🔗 建立软链: {pt} → {zf.name}")
    elif delete_original:
        pt.unlink(missing_ok=True)
        print(f"🗑️ 删除原始 .pt: {pt}")

def batch_convert(root, mode="zip", delete=False):
    root = Path(root).expanduser()
    if not root.is_dir():
        raise SystemExit(f"❌ 目录不存在: {root}")
    for p in root.rglob("*.pt"):
        convert_one(p, mode=mode, delete_original=delete)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="模型根目录")
    ap.add_argument("--mode", choices=["zip", "inplace", "link"], default="zip",
                    help="zip=生成.zip; inplace=覆盖.pt; link=软链.pt→.zip")
    ap.add_argument("--delete", action="store_true",
                    help="zip 模式下删除原 .pt 文件")
    args = ap.parse_args()
    batch_convert(args.dir, mode=args.mode, delete=args.delete)
    print("✅ 全部处理完毕")