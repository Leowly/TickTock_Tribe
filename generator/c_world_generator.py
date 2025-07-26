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
        lib_name = None
        src_path = os.path.join(os.path.dirname(__file__), "generator.cpp")

        if sys.platform.startswith("win"):
            lib_name = os.path.join(os.path.dirname(__file__), "generator.dll")
            compile_cmd = [
                "g++",
                "-shared",
                "-o",
                lib_name,
                "-O2",
                "-static-libgcc",
                "-static-libstdc++",
                "-fPIC",
                src_path,
            ]
        elif sys.platform.startswith("linux"):
            lib_name = os.path.join(os.path.dirname(__file__), "generator.so")
            compile_cmd = ["g++", "-shared", "-fPIC", "-O2", src_path, "-o", lib_name]
        else:
            raise RuntimeError("Unsupported platform")

        if not os.path.exists(lib_name):
            print(f"🔧 Compiling C++ library: {lib_name}")
            try:
                subprocess.run(compile_cmd, check=True)
                print("✅ Compilation successful")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"❌ Failed to compile C++ library: {e}")

        self.lib = ctypes.CDLL(lib_name)
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

