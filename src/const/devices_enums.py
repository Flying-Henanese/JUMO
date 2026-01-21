from enum import Enum

class DeviceType(Enum):
    """
    指定设备类型
    """
    CPU = 'cpu'
    NPU = 'npu'
    MPS = 'mps'
    CUDA = 'cuda'

def device_type_values() -> list[str]:
    """
    返回枚举中定义的所有设备类型的值列表
    """
    return [member.value for member in DeviceType]
