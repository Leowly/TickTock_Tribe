import os
import tomli
from flask import Flask, jsonify, render_template
from c_world_generator import generate_world_from_c
import time

app = Flask(__name__)

# 加载配置文件
config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
with open(config_path, 'rb') as f:
    config = tomli.load(f)

# 从配置文件中读取参数
MAX_VISIBLE_PIXELS = config['map']['max_visible_pixels']

FOREST_GENERATION_PARAMS = config['terrain']['forest']
WATER_GENERATION_PARAMS = config['terrain']['water']

class World:
    _instance = None
    _is_initializing = False

    def __init__(self, width, height, forest_params, water_params):
        if not World._is_initializing:
            raise RuntimeError("请使用 World.initialize() 创建实例")
        self.width = width
        self.height = height
        self.forest_params = forest_params
        self.water_params = water_params
        self._grid = None
        self.generation_time = 0
        self.generation_status = "未生成"

    @classmethod
    def initialize(cls, width, height, forest_params, water_params):
        if cls._instance is None:
            cls._is_initializing = True
            cls._instance = cls(width, height, forest_params, water_params)
            cls._is_initializing = False
        return cls._instance

    @staticmethod
    def print_status_message(message):
        print(f"\n=== 世界地图状态 ===")
        print(message)
        print("=================\n")

    @property
    def grid(self):
        if self._grid is None:
            self.generation_status = "生成中..."
            self.print_status_message(self.generation_status)
            
            start_time = time.time()
            self._grid = generate_world_from_c(
                self.width, self.height, 
                self.forest_params, self.water_params
            )
            
            self.generation_time = time.time() - start_time
            self.generation_status = f"生成完成！耗时: {self.generation_time:.2f} 秒\n地图大小: {self.width}x{self.height}"
            self.print_status_message(self.generation_status)

        return self._grid

GAME_WORLD = World.initialize(
    width=config['map']['width'],
    height=config['map']['height'],
    forest_params=FOREST_GENERATION_PARAMS,
    water_params=WATER_GENERATION_PARAMS
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/world')
def get_world_data():
    world_data = {
        'width': GAME_WORLD.width,
        'height': GAME_WORLD.height,
        'grid': GAME_WORLD.grid,
        'generation_time': GAME_WORLD.generation_time,
        'max_visible_pixels': MAX_VISIBLE_PIXELS
    }
    return jsonify(world_data)

# 使用列表来跟踪启动状态
startup_status = [True]

if __name__ == '__main__':
    if startup_status[0]:
        print("\n=== 首次服务器启动 ===")
        print("预生成地图...")
        # 预加载地图
        _ = GAME_WORLD.grid
        startup_status[0] = False
    else:
        print("\n=== 服务器重新加载 ===")
    
    print("启动 Web 服务器...")
    app.run(
        host=config['server']['host'],
        port=config['server']['port'],
        debug=config['server']['debug']
    )