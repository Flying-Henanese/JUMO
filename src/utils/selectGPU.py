import pynvml

def get_gpu_with_max_free_memory():
    pynvml.nvmlInit()
    device_count = pynvml.nvmlDeviceGetCount()

    max_free_mem = 0
    selected_gpu_index = 0

    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        free_mem = mem_info.free
        if free_mem > max_free_mem:
            max_free_mem = free_mem
            selected_gpu_index = i

    pynvml.nvmlShutdown()
    return selected_gpu_index
