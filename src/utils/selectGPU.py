import pynvml
from typing import List
from dataclasses import dataclass
import torch
import psutil
import os
from loguru import logger
from dotenv import load_dotenv
from const.devices_enums import DeviceType
load_dotenv()
MINIMUM_GPU_MEMORY = int(os.getenv('MINIMUM_GPU_MEMORY', 8*1024**3))

@dataclass
class GPUInfo:
    index: int
    free_mem: int
    total_mem: int
    device_type: DeviceType = DeviceType.CPU # 默认肯定是CPU，所有设备都有CPU  
    is_running: bool = False
    
    @property
    def utilization(self) -> float:
        """计算GPU利用率并保留2位小数"""
        if self.total_mem == 0:
            return 0.0
        return round((1 - self.free_mem / self.total_mem) * 100, 2)

    @property # 为了像使用属性一样调用这个函数,有点像是添加了一个虚拟属性
    def free_percent(self) -> float:
        return (self.free_mem / self.total_mem) * 100
    
    @property
    def free_mem_str(self) -> str:
        return f'{self.free_mem / 1024**3:.2f}GB'
    
    @property
    def total_mem_str(self) -> str:
        return f'{self.total_mem / 1024**3:.2f}GB'

    def __repr__(self) -> str:
        return f'GPUInfo(index={self.index}, free_mem={self.free_mem}, total_mem={self.total_mem}, utilization={self.utilization})'

class GPUPool:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, min_free_mem: int = MINIMUM_GPU_MEMORY):
        '''
        初始化GPU池,默认最小显存为 MINIMUM_GPU_MEMORY
        只有显存超过阈值的GPU才会被选中加入到资源池
        '''
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self.min_free_mem = min_free_mem
        self.available_gpus: List[GPUInfo] = []  # 使用GPUInfo类替代字典
    
    def refresh(self) -> None: # 很幸运的是，这个函数只有在没有可用GPU时才会被调用
        '''
        刷新GPU池,获取当前可用的GPU列表
        '''
        try:
            # 是的，这里真的需要显式 import torch_npu，即便你后面用的是 torch.npu。原因如下：
            # torch_npu 是个 外部扩展模块，它注册了NPU设备到 torch 中；
            # 如果不先导入 torch_npu，则 torch.npu 根本不存在，会报错。
            import torch_npu
            if torch.npu.is_available() and os.getenv('MINERU_DEVICE_MODE') == 'npu':
                # 这里先把所有检测到的NPU设备加入到资源池
                # 反正现在只有我适配910B的NPU
                for device_id in range(torch.npu.device_count()):
                    # torch.npu.set_device(device_id)
                    free_npu_memory = self._get_npu_free_memory(device_id=device_id)
                    if free_npu_memory >= self.min_free_mem: 
                        self.available_gpus.append(
                            GPUInfo(
                                index=device_id,
                                free_mem=free_npu_memory,
                                # 910B的单卡内存是64GB了
                                # 暂时还没有找到获取NPU内存的函数，只能先写死了
                                total_mem=64*1024**3, 
                                device_type='NPU'
                            )
                        ) 
            return
        except ImportError:
            pass  # 没有安装 torch-npu，则跳过 NPU 支持
        if torch.backends.mps.is_available() and os.getenv('MINERU_DEVICE_MODE') == 'mps':
            # MPS设备处理逻辑
            mem = psutil.virtual_memory()
            self.available_gpus = [
                GPUInfo(
                    index=0, 
                    free_mem=mem.available, 
                    total_mem=mem.total, 
                    device_type=DeviceType.MPS
                    )
                ]
        elif torch.cuda.is_available() and os.getenv('MINERU_DEVICE_MODE') == 'cuda':
            pynvml.nvmlInit()
            self.available_gpus = []
            
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                if mem_info.free >= self.min_free_mem:
                    self.available_gpus.append(
                        GPUInfo(
                            index=i,
                            free_mem=mem_info.free,
                            total_mem=mem_info.total,
                            device_type=DeviceType.CUDA
                        )
                    )
            pynvml.nvmlShutdown() 
        else:
            self.available_gpus = [
                GPUInfo(
                    index=0, 
                    free_mem=0, 
                    total_mem=0, 
                    device_type=DeviceType.CPU
                    )
                ]
        self.available_gpus.sort(key=lambda x: x.free_mem, reverse=True)
        logger.info(f'当前可用GPU列表: {self.available_gpus}')
 
    def get_best_gpu(self) -> GPUInfo:
        """获取当前最优GPU"""
        if not self.available_gpus:
            self.refresh()
        # 已经刷新过，再试一下看看有没有可用的GPU/NPU
        if not self.available_gpus:
            logger.warning("没有可用的GPU设备")
            return None
        elif self.available_gpus[0].free_mem < self.min_free_mem:
            logger.warning(f'显存不足，当前最优GPU显存利用率为{self.available_gpus[0].utilization}%')
            return None # 没有充足的显存运行任务
        logger.info(f'选择:{self.available_gpus[0].device_type}-{self.available_gpus[0]} 执行任务')
        return self.available_gpus[0] 
    
    def get_available_gpus(self) -> List[GPUInfo]:
        """获取所有符合条件的GPU列表"""
        if not self.available_gpus:
            self.refresh()
        return self.available_gpus

    def _get_npu_free_memory(self, device_id: int = 0) -> int:
        """返回指定 NPU 设备的空闲内存(单位在此不做转换，在显示的时候再使用GB)"""
        torch.npu.set_device(device_id)
        total_memory = torch.npu.get_device_properties(device_id).total_memory  # 总内存（字节）
        reserved_memory = torch.npu.memory_reserved(device_id)                  # 已预留内存（字节）
        free_memory = total_memory - reserved_memory
        return free_memory # // (1024 ** 3)  # 转为 GB
