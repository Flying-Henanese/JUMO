#!/usr/bin/env python3
"""
批量将 .pt/.pth（旧格式）与 .safetensors 转为 PyTorch zip-serialization，
并验证能否在 NPU 上加载。已是 zip 格式的 .pt/.pth 仅做验证。
用法：
  python convert_models_to_zip_npu.py --path <文件或目录>
"""
import argparse, os, subprocess, importlib, dill
from pathlib import Path
from collections import OrderedDict
import acl  # 华为 CANN 提供的 Python API
# 先导入 torch_npu，再导入 torch
import torch_npu                # Ascend 环境必需
import torch
from safetensors.torch import safe_open  # 仅在处理 .safetensors 时用

# ---------- 工具函数 ----------
def is_zip(path: str) -> bool:
    '''
    使用Linux命令验证文件是否已经转换为zip格式
    '''
    try:
        out = subprocess.check_output(["file", "-b", path]).decode()
        return "Zip archive data" in out
    except Exception:
        return False

def add_safe_globals(pt_file: str):
    """注册自定义类，避免 torch.load 反序列化失败"""
    try:
        """
        这行代码会分析模型文件( .pt 或 .pth )
        返回一个包含所有"不安全"全局变量(类/函数)的列表
        这些是在模型保存时被pickle记录但可能不存在于当前运行环境的对象
        """
        unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(pt_file)
        
        # 创建空列表存储安全全局变量
        safe_globals = []
        
        # 遍历所有不安全的全局变量
        for fully_qualified_name in unsafe:
            # 分割模块路径和类名
            module_path, _, class_name = fully_qualified_name.rpartition('.')
            
            # 确保模块路径和类名有效
            if module_path and class_name:
                try:
                    # 动态导入模块
                    module = importlib.import_module(module_path)
                    # 获取类对象
                    class_obj = getattr(module, class_name)
                    # 添加到安全列表
                    safe_globals.append(class_obj)
                except ImportError as e:
                    print(f"无法导入模块 {module_path}: {e}")
                    continue
        
        # 添加dill的_load_type以支持自定义类型
        safe_globals.append(dill._dill._load_type)
        
        # 注册所有安全全局变量
        torch.serialization.add_safe_globals(safe_globals)
    except Exception:
        pass

# ---------- 核心处理 ----------
def convert_pt_like_inplace(file_path: Path):
    """将旧 pickle-pt/pth 转为 zip-pt/pth（覆盖保存）"""
    # 注册安全全局变量，避免 torch.load 反序列化失败
    add_safe_globals(str(file_path))
    # 为了保证转换可以成功，所以这里使用cpu加载，不影响后续推理过程的加速
    ckpt = torch.load(file_path, map_location="cpu")
    # 创建一个临时文件路径
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    # 保存转换后的模型到临时文件
    torch.save(ckpt, tmp, _use_new_zipfile_serialization=True)
    # 验证转换过后的模型文件是否已经为zip格式(虽然后缀名不变)
    # 如果没有通过验证，则删除临时文件，并抛出异常
    if not is_zip(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("保存后仍非 zip 格式！")
    os.replace(tmp, file_path)

def convert_safetensors(file_path: Path) -> Path:
    """把 .safetensors → 同名 .pt（zip）"""
    out_pt = file_path.with_suffix(".pt")
    if out_pt.exists():
        print(f"⚠️  目标文件已存在，跳过写入: {out_pt}")
        return out_pt
    st = OrderedDict()
    # 使用 safe_open 安全打开 .safetensors 文件
    # 指定框架为PyTorch( framework="pt" )
    # 强制使用CPU设备( device="cpu" )避免兼容问题
    with safe_open(file_path, framework="pt", device="cpu") as f:
        for k in f.keys(): # 遍历模型中所有的张量键
            st[k] = f.get_tensor(k) # 获取对应的张量并存入目标字典
    # 下面的逻辑和上面处理pt文件的逻辑类似
    torch.save(st, out_pt, _use_new_zipfile_serialization=True)
    if not is_zip(out_pt):
        out_pt.unlink(missing_ok=True)
        raise RuntimeError("转换失败，生成文件非 zip 格式")
    return out_pt

# 处理 ONNX 模型
# 和pytorch相关的模型不同
def convert_onnx_to_om(onnx_path: Path, soc="Ascend910B", batch=1):
    om_path = onnx_path.with_suffix(".om")
    if om_path.exists():
        print(f"✅ 已有 OM: {om_path.name}")
        return om_path

    cmd = [
        "atc",
        f"--model={onnx_path}",
        "--framework=5",                 # 5 = ONNX
        f"--output={om_path.with_suffix('')}",
        f"--input_format=ND",
        f"--input_shape=\"input:{batch},3,224,224\"",
        f"--soc_version={soc}"
    ]
    print("🚀 运行 ATC:", " ".join(cmd))
    subprocess.run(" ".join(cmd), shell=True, check=True)
    if not om_path.exists():
        raise RuntimeError("ATC 转换失败，未生成 .om")
    return om_path

def validate_npu_load(file_path: Path):
    try:
        torch.load(file_path, map_location="npu:0")  # 抛异常即失败
        return True
    except Exception as e:
        print(f"❌ NPU 加载失败: {file_path.name}\n{e}")
        return False

def validate_acl_load(om_path: Path):
    import acl      # Ascend CANN Python API
    acl.init()
    try:
        model_desc, model_id = acl.mdl.load_from_file(str(om_path))
        acl.mdl.unload(model_id)
        acl.finalize()
        return True
    except Exception as e:
        print("❌ ACL 加载失败:", e)
        acl.finalize()
        return False

def process_file(file_path: Path):
    suffix = file_path.suffix.lower()
    try:
        if suffix in {".pt", ".pth"}:
            if is_zip(file_path):
                print(f"✅ 已是 zip: {file_path.name}")
            else:
                print(f"🔄 转换 {file_path.name} → zip")
                convert_pt_like_inplace(file_path)
        elif suffix == ".safetensors":
            print(f"🔄 转换 {file_path.name} → .pt (zip)")
            file_path = convert_safetensors(file_path)
        elif suffix == ".onnx":
            print(f"🔄 ATC 转换 {file_path.name} → .om")
            om_path = convert_onnx_to_om(file_path)
            # 可选：用 acl / onnxruntime‑cann 进行一次推理验证
            if validate_acl_load(om_path):
                print(f"🎉 OM 加载成功: {om_path.name}\n")        
        else:
            print(f"⏭️  跳过不支持格式: {file_path.name}")
            return
        # NPU 验证
        if validate_npu_load(file_path):
            print(f"🎉 NPU 加载成功: {file_path.name}\n")
        else:
            print(f"❌ NPU 加载失败: {file_path.name}\n")
    except Exception as e:
        print(f"❌ 处理失败 {file_path.name}: {e}\n")

def recursive_process(path: Path):
    if path.is_file():
        process_file(path)
    else:
        for p in path.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".pt", ".pth", ".safetensors"}:
                process_file(p)

# ---------- CLI ----------
if __name__ == "__main__":
    # 
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True,
                    help="模型文件或包含模型的目录")
    args = ap.parse_args()
    tgt = Path(args.path).expanduser().resolve()
    if not tgt.exists():
        raise SystemExit(f"❌ 路径不存在: {tgt}")
    recursive_process(tgt)
    print("✅ 全部处理完成")