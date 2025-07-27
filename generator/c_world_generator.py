# generator/c_world_generator.py
import os
import sys
import ctypes
import subprocess
from ctypes import c_int, c_double, POINTER, Structure, c_uint8

# --- 新增：定义与 C++ PackedMapResult 对应的 ctypes 结构 ---
class PackedMapResult(Structure):
    _fields_ = [
        ("data", POINTER(c_uint8)),  # 指向打包数据的指针
        ("size", c_int)             # 打包数据的大小（字节数）
    ]
# --- 新增结束 ---


class ForestParams(Structure):
    _fields_ = [
        ("seed_prob", c_double),
        ("iterations", c_int),
        ("birth_threshold", c_int),
    ]


class WaterParams(Structure):
    _fields_ = [
        ("density", c_double),
        ("turn_prob", c_double),
        ("stop_prob", c_double),
        ("height_influence", c_double),
    ]


class CWorldGenerator:
    def __init__(self):
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(__file__)
        
        # 构建完整的文件路径
        src_path = os.path.join(current_dir, "generator.cpp")
        lib_name = None

        if sys.platform.startswith("win"):
            lib_name = os.path.join(current_dir, "generator.dll")
            compile_cmd = [
                "g++",
                "-shared",
                "-o",
                lib_name,
                src_path,  # 使用完整路径
                "-O2",
                "-std=c++11",
                "-static",
                "-static-libgcc",
                "-static-libstdc++"
            ]
        elif sys.platform.startswith("linux"):
            lib_name = os.path.join(current_dir, "generator.so")
            compile_cmd = [
                "g++", 
                "-shared", 
                "-fPIC", 
                "-O2", 
                src_path,  # 使用完整路径
                "-o", 
                lib_name
            ]
        else:
            raise RuntimeError("Unsupported platform")

        # 检查源文件是否存在
        if not os.path.exists(src_path):
            raise RuntimeError(f"Source file not found: {src_path}")
        
        # 如果DLL/so不存在，则编译
        if not os.path.exists(lib_name):
            print(f"🔧 Compiling C++ library: {lib_name}")
            try:
                # 在正确的目录下执行编译命令
                subprocess.run(compile_cmd, check=True, cwd=current_dir)
                print("✅ Compilation successful")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"❌ Failed to compile C++ library: {e}")
            except FileNotFoundError:
                raise RuntimeError("❌ g++ compiler not found. Please install MinGW-w64 or GCC.")

        # 加载DLL/so
        try:
            self.lib = ctypes.CDLL(lib_name)
            print(f"✅ Loaded library: {lib_name}")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to load library {lib_name}: {e}")

        # --- 修改开始：设置新的函数签名 ---
        # 保留原有的 generate_map 签名（如果需要的话）
        self.lib.generate_map.restype = POINTER(c_uint8)
        self.lib.generate_map.argtypes = [c_int, c_int, ForestParams, WaterParams]
        
        # 设置新函数 generate_map_packed 的签名
        # 返回一个 PackedMapResult 结构体
        self.lib.generate_map_packed.restype = PackedMapResult
        # 参数类型与 generate_map 相同
        self.lib.generate_map_packed.argtypes = [c_int, c_int, ForestParams, WaterParams]
        
        # 保留 free_map 的签名，用于释放 generate_map 或 packed data (作为 uint8_t*)
        self.lib.free_map.argtypes = [POINTER(c_uint8)]
        # --- 修改结束 ---


    def generate_tiles(
        self,
        width,
        height,
        seed_prob,
        forest_iterations,
        forest_birth_threshold,
        water_density,
        water_turn_prob,
        water_stop_prob,
        water_height_influence,
    ):
        f_params = ForestParams(seed_prob, forest_iterations, forest_birth_threshold)
        w_params = WaterParams(
            water_density, water_turn_prob, water_stop_prob, water_height_influence
        )

        # --- 修改开始：调用新的打包函数 ---
        # 调用 C++ 的 generate_map_packed 函数
        result = self.lib.generate_map_packed(width, height, f_params, w_params)
        
        # 检查生成是否成功 (通过检查 data 指针是否为 NULL)
        if not result.data:
            raise RuntimeError("Map generation failed in C++ generate_map_packed")
            
        # 从 result.data 指针读取 result.size 字节的数据
        # ctypes.string_at 会创建一个 Python bytes 对象的副本
        packed_map_bytes = ctypes.string_at(result.data, result.size)
        
        # 重要：释放 C++ 中分配的内存
        # 注意：我们传递的是 result.data（一个指针），而不是 result 本身
        self.lib.free_map(result.data)
        
        # 返回打包好的 bytes 对象
        return packed_map_bytes
        # --- 修改结束 ---
