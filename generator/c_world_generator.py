import os
import sys
import ctypes
import subprocess
from ctypes import c_int, c_double, POINTER, Structure, c_uint8


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
        
        # 如果DLL不存在，则编译
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

        # 加载DLL
        try:
            self.lib = ctypes.CDLL(lib_name)
            print(f"✅ Loaded library: {lib_name}")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to load library {lib_name}: {e}")

        # 设置函数签名
        self.lib.generate_map.restype = POINTER(c_uint8)
        self.lib.generate_map.argtypes = [c_int, c_int, ForestParams, WaterParams]
        self.lib.free_map.argtypes = [POINTER(c_uint8)]

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

        ptr = self.lib.generate_map(width, height, f_params, w_params)
        if not ptr:
            raise RuntimeError("Map generation failed")

        size = width * height
        tiles = [ptr[i] for i in range(size)]

        self.lib.free_map(ptr)
        return tiles