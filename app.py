# app.py
from flask import Flask, request, jsonify, render_template
import logging
from core.config import Config
from generator.c_world_generator import CWorldGenerator
from core import database
from core import world_updater # 只导入模块
from core.ticker import Ticker      # 只导入类

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import base64

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
        "tasks": config.get_tasks(),
        "farming": config.get_farming(),
        "housing": config.get_housing(),
        "ai": config.get_ai(),
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
    """
    生成新地图。初始村民将在第一个tick时由VillagerManager自动创建。
    """
    data = request.json or {}
    try:
        # --- 1. 解析请求参数 ---
        name = data["name"]
        world_params = data["world"]
        forest_params = data["forest"]
        water_params = data["water"]

        width = int(world_params["width"])
        height = int(world_params["height"])
        
        # --- 2. 调用 C++ 生成器创建地形 ---
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
        
        # --- 3. 将新地图存入数据库 ---
        map_id = database.insert_map(name, width, height, packed_map_bytes)
        if not map_id:
            return jsonify({"error": "Failed to save new map to database"}), 500

        # --- 4. 返回成功响应 ---
        return jsonify({
            "success": True,
            "map_id": map_id,
            "name": name,
            "message": f"Map created successfully. Initial villagers will be created when simulation starts."
        }), 201 # 201 Created
        
    except KeyError as e:
        return jsonify({"error": f"Missing required parameter in request: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Map generation failed unexpectedly: {e}", exc_info=True)
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


@app.route("/api/maps/<int:map_id>/villagers", methods=["GET"])
def get_villagers(map_id):
    """获取指定地图的村民数据"""
    #--------- 开始新增 ---------
    ticker_instance.update_activity(map_id) # 每次请求都更新活动时间，作为心跳
    #--------- 结束新增 ---------

    snapshot = database.get_world_snapshot(map_id)
    if not snapshot:
        # 如果快照不存在，可能是模拟刚开始，返回空数据而不是错误
        return jsonify({"villagers": [], "houses": []})
    
    # 使用VillagerManager获取村民数据
    villager_manager = world_updater_instance.villager_manager
    # 从数据库快照加载村民数据
    villager_manager.load_from_database(snapshot)
    villagers_data = villager_manager.get_villagers_data()
    houses_data = villager_manager.get_houses_data()
    
    return jsonify({
        "villagers": villagers_data,
        "houses": houses_data
    })


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
            "FARM_MATURE (4)": stats.get(4, 0),
        },
        "entity_counts": {
            "villagers": len(snapshot.villagers), "houses": len(snapshot.houses)
        }
    })


@app.route("/api/villagers/<int:villager_id>", methods=["GET"])
def get_single_villager(villager_id):
    """【新增】获取单个村民的详细信息"""
    villager_data = database.get_villager_by_id(villager_id)
    if not villager_data:
        return jsonify({"error": "Villager not found"}), 404
    return jsonify(villager_data)


@app.route("/api/houses/<int:house_id>", methods=["GET"])
def get_single_house(house_id):
    """【新增】获取单个房屋的详细信息"""
    house_data = database.get_house_by_id(house_id)
    if not house_data:
        return jsonify({"error": "House not found"}), 404
    return jsonify(house_data)

@app.route("/api/simulation_speed", methods=["POST"])
def set_simulation_speed():
    """【新增】设置模拟速度"""
    data = request.json
    if not data or "speed" not in data:
        return jsonify({"error": "Missing 'speed' parameter"}), 400
    
    try:
        speed_multiplier = float(data["speed"])
        if speed_multiplier < 0:
            return jsonify({"error": "Speed multiplier cannot be negative"}), 400
        
        # 调用ticker实例的方法来设置速度
        ticker_instance.set_speed(speed_multiplier)
        
        return jsonify({"success": True, "message": f"Simulation speed set to {speed_multiplier}x"})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid 'speed' parameter, must be a number"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=16151, debug=False)