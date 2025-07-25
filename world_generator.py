import random

# --- 地块类型定义 ---
PLAIN = 0
FOREST = 1
WATER = 2

class World:
    """
    管理游戏世界地图的类，包括地形生成。
    """
    def __init__(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("Width and height must be positive integers.")
        self.width = width
        self.height = height
        self.grid = [[PLAIN for _ in range(width)] for _ in range(height)]

    def _is_within_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    # 内部函数保持不变，它们依然有自己的默认值，方便独立测试
    def _generate_forests(self, seed_prob=0.28, iterations=4, birth_threshold=5, verbose=False):
        if verbose:
            print(f"开始生成森林... (种子概率: {seed_prob}, 生长阈值: {birth_threshold})")
        for y in range(self.height):
            for x in range(self.width):
                if random.random() < seed_prob:
                    self.grid[y][x] = FOREST
        for i in range(iterations):
            new_grid = [row[:] for row in self.grid]
            for y in range(self.height):
                for x in range(self.width):
                    forest_neighbors = 0
                    for dy in [-1, 0, 1]:
                        for dx in [-1, 0, 1]:
                            if dy == 0 and dx == 0: continue
                            nx, ny = x + dx, y + dy
                            if self._is_within_bounds(nx, ny) and self.grid[ny][nx] == FOREST:
                                forest_neighbors += 1
                    if self.grid[y][x] == PLAIN and forest_neighbors >= birth_threshold:
                        new_grid[y][x] = FOREST
            self.grid = new_grid
        if verbose: print("森林生成完毕。")

    def _generate_water_system(self, density=0.001, turn_prob=0.1, stop_prob=0.05, verbose=False):
        num_sources = max(1, int(self.width * self.height * density))
        if verbose:
            print(f"开始生成水系... (水源点密度: {density}, 计算数量: {num_sources})")
        turn_map = { (0, 1):  {'left': (1, 0),  'right': (-1, 0)}, (0, -1): {'left': (-1, 0), 'right': (1, 0)}, (1, 0):  {'left': (0, -1), 'right': (0, 1)}, (-1, 0): {'left': (0, 1),  'right': (0, -1)} }
        for i in range(num_sources):
            sx, sy = random.randint(0, self.width - 1), random.randint(0, self.height - 1)
            if self.grid[sy][sx] == WATER: continue
            self.grid[sy][sx] = WATER
            initial_directions = random.sample(list(turn_map.keys()), 2)
            for branch in range(2):
                cx, cy = sx, sy
                direction = initial_directions[branch]
                while True:
                    if random.random() < stop_prob: break
                    rand_val = random.random()
                    if rand_val < turn_prob: direction = turn_map[direction]['left']
                    elif rand_val < turn_prob * 2: direction = turn_map[direction]['right']
                    nx, ny = cx + direction[0], cy + direction[1]
                    if not self._is_within_bounds(nx, ny): break
                    cx, cy = nx, ny
                    self.grid[cy][cx] = WATER
        if verbose: print("水系生成完毕。")

    # --- 核心修改点在这里 ---
    def generate_terrain(self, forest_params, water_params, verbose=False):
        if verbose: print("--- 开始生成地形 ---")

        self.grid = [[PLAIN for _ in range(self.width)] for _ in range(self.height)]
        
        # 使用传入的参数调用内部生成函数
        # `**` 操作符会将字典解包为关键字参数
        self._generate_forests(**forest_params, verbose=verbose)
        self._generate_water_system(**water_params, verbose=verbose)
        
        if verbose: print("--- 地形数据生成完成 ---")
        return

    def display(self):
        tile_map = { PLAIN: '🟨', FOREST: '🟩', WATER: '🟦' }
        print("\n--- 当前世界地图 ---")
        for y in range(self.height):
            row_str = "".join([tile_map.get(self.grid[y][x], '❓') for x in range(self.width)])
            print(row_str)

# --- 主程序入口也需要更新，以演示新的调用方式 ---
if __name__ == '__main__':
    # 定义参数
    fp = {
        'seed_prob': 0.05,
        'iterations': 3,
        'birth_threshold': 2
    }
    wp = {
        'density': 0.002,
        'turn_prob': 0.3,
        'stop_prob': 0.004
    }
    
    # 创建世界
    world = World(width=75, height=120)
    
    # 使用新的方式生成地形
    world.generate_terrain(forest_params=fp, water_params=wp, verbose=True)
    
    world.display()