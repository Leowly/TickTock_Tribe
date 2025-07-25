import os
import sys
import ctypes
from ctypes import c_int, c_double, POINTER, Structure, c_uint8

class ForestParams(Structure):
    _fields_ = [
        ('seed_prob', c_double),
        ('iterations', c_int),
        ('birth_threshold', c_int)
    ]

class WaterParams(Structure):
    _fields_ = [
        ('density', c_double),
        ('turn_prob', c_double),
        ('stop_prob', c_double),
        ('height_influence', c_double)
    ]

class CWorldGenerator:
    def __init__(self):
        lib_name = None
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if sys.platform.startswith('win'):
            lib_name = os.path.join(base_dir, 'generator', 'c_world_generator.dll')
        elif sys.platform.startswith('linux'):
            lib_name = os.path.join(base_dir, 'generator', 'libc_world_generator.so')
        else:
            raise RuntimeError("Unsupported platform")


        self.lib = ctypes.CDLL(lib_name)
        self.lib.generate_map.restype = POINTER(c_uint8)
        self.lib.generate_map.argtypes = [
            c_int, c_int, ForestParams, WaterParams
        ]
        self.lib.free_map.argtypes = [POINTER(c_uint8)]

    def generate_tiles(self, width, height,
                       seed_prob, forest_iterations, forest_birth_threshold,
                       water_density, water_turn_prob, water_stop_prob, water_height_influence):
        f_params = ForestParams(seed_prob, forest_iterations, forest_birth_threshold)
        w_params = WaterParams(water_density, water_turn_prob, water_stop_prob, water_height_influence)

        ptr = self.lib.generate_map(width, height, f_params, w_params)
        if not ptr:
            raise RuntimeError("Map generation failed")

        # 拷贝返回的数组内容
        size = width * height
        tiles = [ptr[i] for i in range(size)]

        self.lib.free_map(ptr)
        return tiles
