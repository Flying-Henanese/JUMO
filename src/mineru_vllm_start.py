import os
import signal
import subprocess
import sys
import time
import argparse
from pathlib import Path

from loguru import logger

from utils.auto_device_selector import get_env_vars_for_device


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_device() -> str:
    direct = os.getenv("INFERENCE_DEVICE", "").strip()
    if direct:
        return direct
    devices_raw = os.getenv("INFERENCE_DEVICES", "").strip()
    if devices_raw:
        return devices_raw.split(",")[0].strip()
    return "0"


def _build_cmd(python_bin: str, port: int, host: str) -> list[str]:
    model = os.getenv("MODEL", "opendatalab/MinerU2.5-2509-1.2B")
    tensor_parallel_size = os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "1")
    gpu_memory_utilization = os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.8")
    cmd = [
        python_bin,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        model,
        "--host",
        host,
        "--port",
        str(port),
        "--tensor-parallel-size",
        str(tensor_parallel_size),
        "--gpu-memory-utilization",
        str(gpu_memory_utilization),
        "--trust-remote-code",
    ]
    extra = os.getenv("VLLM_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())
    return cmd


def daemonize():
    """将进程转为后台运行"""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"fork #1 failed: {e}")
        sys.exit(1)

    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"fork #2 failed: {e}")
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="MinerU vLLM Start Script")
    parser.add_argument("--daemon", action="store_true", help="Run in background")
    args = parser.parse_args()

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("VLLM_USE_MODELSCOPE", "True")
    os.environ.setdefault("VLLM_RPC_TIMEOUT", "600000")

    host = os.getenv("VLLM_HOST", "0.0.0.0")
    port = int(os.getenv("VLLM_PORT", "8000"))
    device_id = _resolve_device()

    root = _project_root()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.daemon:
        logger.info("Daemonizing... Output will be redirected to logs/")
        daemonize()

    python_bin = os.getenv("PYTHON_PATH", sys.executable)
    env = os.environ.copy()
    env.update(get_env_vars_for_device(device_id))

    log_file = log_dir / f"vllm_single_dev_{device_id.replace(',', '_')}.log"
    pid_file = log_dir / "vllm_single.pid"
    
    log_fp = open(log_file, "ab", buffering=0)

    cmd = _build_cmd(python_bin, port, host)
    logger.info(
        f"Starting single vLLM instance: device_id={device_id}, host={host}, port={port}, model={os.getenv('MODEL', 'opendatalab/MinerU2.5-2509-1.2B')}"
    )
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
    )

    # 写入 PID 文件
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))

    def _shutdown(signum, _frame) -> None:
        logger.warning(f"Received signal {signum}, stopping vLLM pid={proc.pid}")
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=15)
        except Exception:
            if proc.poll() is None:
                proc.kill()
        if pid_file.exists():
            pid_file.unlink()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        rc = proc.poll()
        if rc is not None:
            logger.error(f"vLLM instance exited: pid={proc.pid}, code={rc}")
            if pid_file.exists():
                pid_file.unlink()
            return int(rc) if isinstance(rc, int) else 1
        time.sleep(1)


if __name__ == "__main__":
    main()