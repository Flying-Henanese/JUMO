from enum import Enum

class DeviceType(Enum):
    """
    指定设备类型
    """
    CPU = 'cpu'
    NPU = 'npu'
    MPS = 'mps'
    CUDA = 'cuda'
