from flask import Flask, jsonify, render_template
from c_world_generator import generate_world_from_c

app = Flask(__name__)

# --- 核心修改点 ---
# 将渲染面积上限提高到一个更合理的值
MAX_VISIBLE_PIXELS = 25000

# --- 您原有的代码保持不变 ---
FOREST_GENERATION_PARAMS = {
    'seed_prob': 0.05,
    'iterations': 3,
    'birth_threshold': 2
}
WATER_GENERATION_PARAMS = {
    'density': 0.002,
    'turn_prob': 0.1,
    'stop_prob': 0.01
}

class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = []

    def generate_terrain(self, forest_params, water_params):
        print("正在通过C库生成世界地图...")
        self.grid = generate_world_from_c(
            self.width, self.height, forest_params, water_params
        )
        print("C库生成完毕。")

GAME_WORLD = World(width=1000, height=1000)
GAME_WORLD.generate_terrain(
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
        'max_visible_pixels': MAX_VISIBLE_PIXELS
    }
    return jsonify(world_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=16151, debug=True)