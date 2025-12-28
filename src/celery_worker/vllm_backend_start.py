import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

from utils.auto_device_selector import get_device_type, get_env_vars_for_device


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _split_devices(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _build_vllm_cmd(python_bin: str, port: int) -> list[str]:
    model = os.getenv("MODEL", "opendatalab/MinerU2.5-2509-1.2B")
    tensor_parallel_size = os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "1")
    gpu_memory_utilization = os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.5")

    cmd = [
        python_bin,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        model,
        "--host",
        "0.0.0.0",
        "--tensor-parallel-size",
        str(tensor_parallel_size),
        "--gpu-memory-utilization",
        str(gpu_memory_utilization),
        "--trust-remote-code",
        "--port",
        str(port),
    ]
    extra = os.getenv("VLLM_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())
    return cmd


def _spawn_instance(
    python_bin: str,
    device_id: str,
    port: int,
    log_dir: Path,
    base_tmp_dir: Path,
) -> subprocess.Popen:
    child_env = os.environ.copy()
    child_env.update(get_env_vars_for_device(device_id))

    instance_tmp_dir = base_tmp_dir / f"dev{device_id.replace(',', '_')}"
    instance_tmp_dir.mkdir(parents=True, exist_ok=True)
    child_env["TMPDIR"] = str(instance_tmp_dir)

    env_hint = ",".join([f"{k}={v}" for k, v in get_env_vars_for_device(device_id).items()]) or "none"
    logger.info(f"Starting vLLM instance: device_id={device_id}, port={port}, env={env_hint}")

    log_file = log_dir / f"vllm_dev{device_id.replace(',', '_')}_port{port}.log"
    log_fp = open(log_file, "ab", buffering=0)

    cmd = _build_vllm_cmd(python_bin, port)
    return subprocess.Popen(
        cmd,
        env=child_env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
    )


def main() -> int:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("VLLM_USE_MODELSCOPE", "True")
    os.environ.setdefault("VLLM_RPC_TIMEOUT", "120000")

    root = _project_root()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    base_tmp_dir = Path(os.getenv("VLLM_TMP_BASE_DIR", "/tmp/vllm_sockets"))
    base_tmp_dir.mkdir(parents=True, exist_ok=True)

    devices_raw = os.getenv("INFERENCE_DEVICES", "").strip()
    if not devices_raw:
        logger.warning("INFERENCE_DEVICES is empty; fallback to '0'")
        devices_raw = "0"
    device_ids = _split_devices(devices_raw)

    base_port = int(os.getenv("VLLM_BASE_PORT", "8000"))
    stagger_s = float(os.getenv("VLLM_STARTUP_STAGGER_SECONDS", "10"))

    python_bin = os.getenv("PYTHON_PATH", sys.executable)
    logger.info(
        f"Launcher config: device_type={get_device_type()}, INFERENCE_DEVICES={devices_raw}, base_port={base_port}, python={python_bin}"
    )

    procs: list[subprocess.Popen] = []

    def _terminate_all() -> None:
        for p in procs:
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass

        deadline = time.time() + 15
        for p in procs:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                p.wait(timeout=remaining)
            except Exception:
                pass

        for p in procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass

    def _handle_signal(signum, _frame) -> None:
        logger.warning(f"Received signal {signum}, stopping vLLM instances...")
        _terminate_all()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        for i, device_id in enumerate(device_ids):
            port = base_port + i
            procs.append(_spawn_instance(python_bin, device_id, port, log_dir, base_tmp_dir))
            if i < len(device_ids) - 1 and stagger_s > 0:
                time.sleep(stagger_s)

        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    logger.error(f"vLLM instance exited: pid={p.pid}, code={rc}. Stopping all...")
                    _terminate_all()
                    return int(rc) if isinstance(rc, int) else 1
            time.sleep(1)
    finally:
        _terminate_all()


if __name__ == "__main__":
    raise SystemExit(main())