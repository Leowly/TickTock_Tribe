from generator.c_world_generator import CWorldGenerator

generator = CWorldGenerator()

def generate_tiles(width, height,
                   seed_prob, forest_iterations, forest_birth_threshold,
                   water_density, water_turn_prob, water_stop_prob, water_height_influence):

    raw_data_flat = generator.generate_tiles(
        width, height,
        seed_prob, forest_iterations, forest_birth_threshold,
        water_density, water_turn_prob, water_stop_prob, water_height_influence
    )

    # 只返回二维数组，不写数据库
    tiles = [raw_data_flat[i * width:(i + 1) * width] for i in range(height)]

    return tiles
