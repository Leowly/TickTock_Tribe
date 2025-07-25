import ctypes
import sys
import os

# --- 1. 定义与C代码匹配的ctypes结构体 ---
class ForestParams(ctypes.Structure):
    _fields_ = [("seed_prob", ctypes.c_double),
                ("iterations", ctypes.c_int),
                ("birth_threshold", ctypes.c_int)]

class WaterParams(ctypes.Structure):
    _fields_ = [("density", ctypes.c_double),
                ("turn_prob", ctypes.c_double),
                ("stop_prob", ctypes.c_double)]

# --- 2. 加载共享库 ---
lib_name = 'generator.dll' if sys.platform == 'win32' else 'libgenerator.so'
lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), lib_name)
try:
    c_lib = ctypes.CDLL(lib_path)
except OSError as e:
    print(f"错误: 无法加载共享库 '{lib_path}'.")
    print("请确保您已经按照说明成功编译了C代码。")
    raise e

# --- 3. 定义C函数原型 (非常重要) ---
# 这能确保ctypes以正确的类型传递和接收数据
c_lib.generate_map.argtypes = [ctypes.c_int, ctypes.c_int, ForestParams, WaterParams]
c_lib.generate_map.restype = ctypes.POINTER(ctypes.c_int)

c_lib.free_map_memory.argtypes = [ctypes.POINTER(ctypes.c_int)]
c_lib.free_map_memory.restype = None

# --- 4. 编写Python友好接口 ---
def generate_world_from_c(width, height, forest_params_dict, water_params_dict):
    """
    调用C库生成世界地图，并将其转换为Python的二维列表。
    """
    # 将Python字典转换为ctypes结构体
    f_params = ForestParams(**forest_params_dict)
    w_params = WaterParams(**water_params_dict)

    # 调用C函数
    map_ptr = c_lib.generate_map(width, height, f_params, w_params)
    
    if not map_ptr:
        raise MemoryError("C代码无法分配地图内存。")

    # 将返回的C指针数据复制到一个Python二维列表中
    grid = []
    for y in range(height):
        row = [map_ptr[y * width + x] for x in range(width)]
        grid.append(row)

    # **关键步骤：释放由C分配的内存，防止内存泄漏！**
    c_lib.free_map_memory(map_ptr)

    return grid