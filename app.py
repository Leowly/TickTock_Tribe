# app.py
from flask import Flask, request, jsonify, render_template
import logging
from core.config import Config
from generator.c_world_generator import CWorldGenerator
from core import database
from core import world_updater
from core.ticker import Ticker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import base64

app = Flask(__name__)

config = Config()
generator = CWorldGenerator()
world_updater_instance = world_updater.WorldUpdater(config_obj=config)
ticker_instance = Ticker(world_updater=world_updater_instance, tick_interval=1.0, inactivity_timeout=120.0) # 延长超时时间

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
    ticker_instance.update_activity(map_id)
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
    maps_data = database.get_maps_list()
    maps = [
        {"id": row[0], "name": row[1], "width": row[2], "height": row[3], "created_at": row[4]}
        for row in maps_data
    ]
    return jsonify(maps)


@app.route("/api/generate_map", methods=["POST"])
def generate_map():
    """【新】生成地图，并立即创建初始村民。"""
    data = request.json or {}
    try:
        name = data["name"]
        world_params = data["world"]
        forest_params = data["forest"]
        water_params = data["water"]

        width = int(world_params["width"])
        height = int(world_params["height"])
        
        # 1. 创建地形
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
        
        # 2. 将新地图存入数据库
        map_id = database.insert_map(name, width, height, packed_map_bytes)
        if not map_id:
            return jsonify({"error": "Failed to save new map to database"}), 500

        # --- 【核心修改】START ---
        # 3. 在地图创建成功后，立即调用新函数来创建初始村民
        try:
            world_updater_instance.villager_manager.create_and_store_initial_villagers(map_id=map_id, width=width, height=height)
            logger.info(f"Successfully created initial villagers for new map {map_id}.")
        except Exception as e:
            # 如果村民创建失败，这虽然不理想，但不应阻止地图的创建
            logger.error(f"Failed to create initial villagers for map {map_id}: {e}", exc_info=True)
        # --- 【核心修改】END ---

        return jsonify({
            "success": True,
            "map_id": map_id,
            "name": name,
            "message": f"Map '{name}' and initial villagers created successfully."
        }), 201
        
    except KeyError as e:
        return jsonify({"error": f"Missing required parameter in request: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Map generation failed unexpectedly: {e}", exc_info=True)
        return jsonify({"error": f"Map generation failed: {str(e)}"}), 500


@app.route("/api/maps/<int:map_id>", methods=["DELETE"])
def delete_map(map_id):
    """【新】删除地图前，先停止对它的模拟。"""
    try:
        # --- 【核心修改】START ---
        # 1. 先通知Ticker停止模拟
        logger.info(f"Received delete request for map {map_id}. Stopping simulation first.")
        ticker_instance.stop_simulation(map_id)
        # --- 【核心修改】END ---

        # 2. 然后再从数据库中删除
        success = database.delete_map(map_id)
        
        if success:
            logger.info(f"Map {map_id} deleted successfully from database.")
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Map not found"}), 404
            
    except Exception as e:
        logger.error(f"An error occurred while deleting map {map_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete map due to an internal error"}), 500


@app.route("/view_map/<int:map_id>")
def view_map(map_id):
    return render_template("map.html")


@app.route("/api/maps/<int:map_id>/start_simulation", methods=["POST"])
def start_simulation(map_id):
    if not database.get_map_by_id(map_id):
        return jsonify({"error": "Map not found"}), 404
    ticker_instance.start_simulation(map_id)
    return jsonify({"success": True, "message": f"Simulation started for map {map_id}"}), 200


@app.route("/api/maps/<int:map_id>/stop_simulation", methods=["POST"])
def stop_simulation(map_id):
    ticker_instance.stop_simulation(map_id)
    return jsonify({"success": True, "message": f"Simulation stopped for map {map_id}"}), 200


@app.route("/api/maps/<int:map_id>/simulation_status", methods=["GET"])
def simulation_status(map_id):
    is_running = ticker_instance.is_simulation_running(map_id)
    current_tick = ticker_instance.get_current_tick(map_id)
    return jsonify({"map_id": map_id, "is_running": is_running, "current_tick": current_tick}), 200


@app.route("/api/maps/<int:map_id>/villagers", methods=["GET"])
def get_villagers(map_id):
    ticker_instance.update_activity(map_id)

    snapshot = database.get_world_snapshot(map_id)
    if not snapshot:
        return jsonify({"villagers": [], "houses": []})
    
    villager_manager = world_updater_instance.villager_manager
    villager_manager.load_from_database(snapshot)
    villagers_data = villager_manager.get_villagers_data()
    houses_data = villager_manager.get_houses_data()
    
    return jsonify({
        "villagers": villagers_data,
        "houses": houses_data
    })

@app.route("/api/villagers/<int:villager_id>", methods=["GET"])
def get_single_villager(villager_id):
    """【新】获取单个村民的详细信息，并附带其仓库信息"""
    villager_data = database.get_villager_by_id(villager_id)
    if not villager_data:
        return jsonify({"error": "Villager not found"}), 404
    
    house_data = database.get_house_by_id(villager_data['house_id'])
    
    if house_data:
        villager_data['food'] = house_data.get('food_storage', 0)
        villager_data['wood'] = house_data.get('wood_storage', 0)
        villager_data['seeds'] = house_data.get('seeds_storage', 0)
        if house_data['x'] is not None:
             villager_data['home_location'] = f"({house_data['x']}, {house_data['y']})"
        else:
             villager_data['home_location'] = "Virtual"

    return jsonify(villager_data)


@app.route("/api/houses/<int:house_id>", methods=["GET"])
def get_single_house(house_id):
    """获取单个房屋的详细信息"""
    house_data = database.get_house_by_id(house_id)
    if not house_data:
        return jsonify({"error": "House not found"}), 404
    return jsonify(house_data)

@app.route("/api/simulation_speed", methods=["POST"])
def set_simulation_speed():
    """设置模拟速度"""
    data = request.json
    if not data or "speed" not in data:
        return jsonify({"error": "Missing 'speed' parameter"}), 400
    
    try:
        speed_multiplier = float(data["speed"])
        if speed_multiplier <= 0:
            return jsonify({"error": "Speed multiplier must be positive"}), 400
        
        ticker_instance.set_speed(speed_multiplier)
        
        return jsonify({"success": True, "message": f"Simulation speed set to {speed_multiplier}x"})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid 'speed' parameter, must be a number"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=16151, debug=False)