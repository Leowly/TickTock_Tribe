# app.py
from flask import Flask, request, jsonify, render_template
from core.config import Config
from generator.c_world_generator import CWorldGenerator
from core import database
from core import world_updater # 只导入模块
from core.ticker import Ticker      # 只导入类
import base64
import random

app = Flask(__name__)

# --- 1. 按顺序装配核心服务 ---
config = Config()
generator = CWorldGenerator()

# 2. 创建 WorldUpdater 实例，它依赖于 config
world_updater_instance = world_updater.WorldUpdater(config_obj=config)

# 3. 创建 Ticker 实例，并将 world_updater_instance 作为依赖注入
ticker_instance = Ticker(world_updater=world_updater_instance, tick_interval=1.0, inactivity_timeout=2.0)

# 4. 初始化数据库
database.init_db()

print("🔧 App initialized successfully using Dependency Injection.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "world": config.get_world(),
        "forest": config.get_forest(),
        "water": config.get_water(),
        "view": config.get_view(),
        "villager": config.get_villager(),
        "time": config.get_time(),
    })


@app.route("/api/maps/<int:map_id>", methods=["GET"])
def get_map(map_id):
    """获取地图渲染数据 (地形)，返回 Base64 编码的 JSON"""
    ticker_instance.update_activity(map_id) # 使用已创建的实例
    map_data = database.get_map_by_id(map_id)
    if not map_data:
        return jsonify({"error": "Map not found"}), 404
    width, height, map_bytes = map_data
    map_data_base64 = base64.b64encode(map_bytes).decode("utf-8")
    return jsonify({
        "id": map_id,
        "width": width,
        "height": height,
        "tiles_base64": map_data_base64,
    })


@app.route("/api/maps", methods=["GET"])
def get_maps():
    """获取地图列表"""
    maps_data = database.get_maps_list()
    maps = [
        {"id": row[0], "name": row[1], "width": row[2], "height": row[3], "created_at": row[4]}
        for row in maps_data
    ]
    return jsonify(maps)


@app.route("/api/generate_map", methods=["POST"])
def generate_map():
    """生成新地图，并根据游戏机制创建初始村民"""
    data = request.json or {}
    try:
        name = data["name"]
        world_params = data["world"]
        forest_params = data["forest"]
        water_params = data["water"]

        width = int(world_params["width"])
        height = int(world_params["height"])
        
        packed_map_bytes = generator.generate_tiles(
            width=width, height=height,
            seed_prob=forest_params["seed_prob"],
            forest_iterations=forest_params["iterations"],
            forest_birth_threshold=forest_params["birth_threshold"],
            water_density=water_params["density"],
            water_turn_prob=water_params["turn_prob"],
            water_stop_prob=water_params["stop_prob"],
            water_height_influence=water_params["height_influence"],
        )
        
        map_id = database.insert_map(name, width, height, packed_map_bytes)
        if not map_id:
            return jsonify({"error": "Failed to save new map to database"}), 500

        villager_config = config.get_villager()
        initial_villager_count = villager_config.get('initial_villagers', 2)
        initial_food = villager_config.get('initial_food', 50)
        
        for i in range(initial_villager_count):
            house_id = database.create_virtual_house(map_id, initial_storage={"food": initial_food})
            if house_id:
                gender = random.choice(['male', 'female'])
                villager_name = f"Pioneer-{i+1}"
                database.insert_villager(map_id, house_id, villager_name, gender)
        
        return jsonify({
            "success": True,
            "map_id": map_id,
            "name": name,
            "message": f"Map created with {initial_villager_count} initial villagers."
        }), 201
        
    except KeyError as e:
        return jsonify({"error": f"Missing required parameter: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Map generation failed: {str(e)}"}), 500


@app.route("/api/maps/<int:map_id>", methods=["DELETE"])
def delete_map(map_id):
    """删除地图"""
    success = database.delete_map(map_id)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Map not found or failed to delete"}), 404


@app.route("/view_map/<int:map_id>")
def view_map(map_id):
    return render_template("map.html")


@app.route("/api/maps/<int:map_id>/start_simulation", methods=["POST"])
def start_simulation(map_id):
    """启动指定地图的模拟"""
    if not database.get_map_by_id(map_id):
        return jsonify({"error": "Map not found"}), 404
    ticker_instance.start_simulation(map_id)
    return jsonify({"success": True, "message": f"Simulation started for map {map_id}"}), 200


@app.route("/api/maps/<int:map_id>/stop_simulation", methods=["POST"])
def stop_simulation(map_id):
    """停止指定地图的模拟"""
    ticker_instance.stop_simulation(map_id)
    return jsonify({"success": True, "message": f"Simulation stopped for map {map_id}"}), 200


@app.route("/api/maps/<int:map_id>/simulation_status", methods=["GET"])
def simulation_status(map_id):
    """获取指定地图的模拟状态"""
    is_running = ticker_instance.is_simulation_running(map_id)
    current_tick = ticker_instance.get_current_tick(map_id)
    return jsonify({"map_id": map_id, "is_running": is_running, "current_tick": current_tick}), 200


@app.route("/api/debug/map_stats/<int:map_id>", methods=["GET"])
def debug_map_stats(map_id):
    """调试接口：返回地图统计数据"""
    snapshot = database.get_world_snapshot(map_id)
    if not snapshot:
        return jsonify({"error": "Map not found"}), 404

    grid_2d = snapshot.grid_2d
    width = snapshot.width
    height = snapshot.height
    
    stats = {i: 0 for i in range(8)}
    for row in grid_2d:
        for tile_value in row:
            if tile_value in stats:
                stats[tile_value] += 1
    
    return jsonify({
        "map_id": map_id, "width": width, "height": height,
        "total_tiles": width * height, "stats": stats,
        "readable_stats": {
            "PLAIN (0)": stats.get(0, 0), "FOREST (1)": stats.get(1, 0),
            "WATER (2)": stats.get(2, 0), "FARM_UNTILLED (3)": stats.get(3, 0),
            "FARM_TILLED (4)": stats.get(4, 0),
        },
        "entity_counts": {
            "villagers": len(snapshot.villagers), "houses": len(snapshot.houses)
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=16151, debug=True)