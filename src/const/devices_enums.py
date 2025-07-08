from enum import Enum

class DeviceType(Enum):
    CPU = 'cpu'
    NPU = 'npu'
    MPS = 'mps'
    CUDA = 'cuda'
