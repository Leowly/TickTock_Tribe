# app.py
from flask import Flask, request, jsonify, render_template
from core.config import Config
from generator.c_world_generator import CWorldGenerator
from core import database
from core.ticker import ticker_instance
from core.world_updater import world_updater_instance
import base64

app = Flask(__name__)

config = Config()
generator = CWorldGenerator()

database.init_db()

# --- 在应用启动时设置是否使用调试逻辑 ---
# 你可以通过配置文件、环境变量或硬编码来控制
USE_DEBUG_LOGIC = False  # <--- 设置为 True 以启用调试逻辑，False 则禁用

# 设置全局实例的 use_debug_logic 属性
world_updater_instance.use_debug_logic = USE_DEBUG_LOGIC
print(
    f"🔧 App initialized. Debug logic is {'ENABLED' if USE_DEBUG_LOGIC else 'DISABLED'}."
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(
        {
            "world": config.get_world(),
            "forest": config.get_forest(),
            "water": config.get_water(),
            "view": config.get_view(),
        }
    )


@app.route("/api/maps/<int:map_id>", methods=["GET"])
def get_map(map_id):
    """获取地图数据，返回包含 Base64 编码数据的 JSON"""
    # --- 在返回数据前，更新该地图的活动时间 ---
    ticker_instance.update_activity(map_id)

    with database.get_connection() as conn:
        cursor = conn.execute(
            "SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,)
        )
        row = cursor.fetchone()
        if not row:
            # 如果找不到地图，返回 JSON 错误和 404 状态码
            return jsonify({"error": "Map not found"}), 404

        width, height, map_bytes = row  # map_bytes 现在是打包后的数据

        # --- 修改：Base64 编码打包后的 bytes ---
        map_data_base64 = base64.b64encode(map_bytes).decode("utf-8")
        # --- 修改结束 ---

        # --- 修改：返回 JSON，包含 Base64 数据 ---
        return jsonify(
            {
                "id": map_id,
                "width": width,
                "height": height,
                # "tiles": tiles_2d # 移除原来的 tiles 字段
                "tiles_base64": map_data_base64,  # 使用新的 Base64 字段，内容是 3-bit 打包数据
            }
        )


@app.route("/api/maps", methods=["GET"])
def get_maps():
    """获取地图列表（不包含实际地图数据）"""
    with database.get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC"
        )
        maps = [
            {
                "id": row[0],
                "name": row[1],
                "width": row[2],
                "height": row[3],
                "created_at": row[4],
            }
            for row in cursor.fetchall()
        ]
    return jsonify(maps)


# --- 修改开始：地图生成接口 ---
@app.route("/api/generate_map", methods=["POST"])
def generate_map():
    """生成新地图并存储打包后的数据"""
    data = request.json or {}

    # 基本校验
    try:
        name = data["name"]
        world_params = data["world"]
        forest_params = data["forest"]
        water_params = data["water"]
    except KeyError as e:
        return jsonify({"error": f"Missing required parameter: {str(e)}"}), 400

    try:
        width = int(world_params["width"])
        height = int(world_params["height"])
        packed_map_bytes = generator.generate_tiles(
            width=width,
            height=height,
            seed_prob=forest_params["seed_prob"],
            forest_iterations=forest_params["iterations"],
            forest_birth_threshold=forest_params["birth_threshold"],
            water_density=water_params["density"],
            water_turn_prob=water_params["turn_prob"],
            water_stop_prob=water_params["stop_prob"],
            water_height_influence=water_params["height_influence"],
        )
    except (KeyError, ValueError, TypeError) as e:
        return jsonify(
            {"error": f"Invalid or missing map generation parameter: {str(e)}"}
        ), 400
    except Exception as e:  # 捕获可能的 C++ 生成器错误
        return jsonify({"error": f"Map generation failed: {str(e)}"}), 500

    map_id = database.insert_map(name, width, height, packed_map_bytes)
    return jsonify(
        {
            "success": True,
            "map_id": map_id,
            "name": name,
            # --- 修改开始 ---
            # 6. 移除 tiles 字段，因为返回的是打包数据，不再是简单的二维列表
            # 'tiles': tiles, # 移除这行
            # --- 修改结束 ---
            "used_params": {
                "world": world_params,
                "forest": forest_params,
                "water": water_params,
            },
        }
    )


# --- 修改结束 ---


@app.route("/api/maps/<int:map_id>", methods=["DELETE"])
def delete_map(map_id):
    """删除地图"""
    with database.get_connection() as conn:
        conn.execute("DELETE FROM world_maps WHERE id=?", (map_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route("/view_map/<int:map_id>")
def view_map(map_id):
    """地图查看页面"""
    return render_template("map.html")


@app.route("/api/maps/<int:map_id>/start_simulation", methods=["POST"])
def start_simulation(map_id):
    """启动指定地图的模拟"""
    # 可以添加检查地图是否存在的逻辑
    map_data_row = database.get_map_by_id(map_id)
    if not map_data_row:
        return jsonify({"error": "Map not found"}), 404

    ticker_instance.start_simulation(map_id)
    return jsonify(
        {"success": True, "message": f"Simulation started for map {map_id}"}
    ), 200


@app.route("/api/maps/<int:map_id>/stop_simulation", methods=["POST"])
def stop_simulation(map_id):
    """停止指定地图的模拟"""
    ticker_instance.stop_simulation(map_id)
    return jsonify(
        {"success": True, "message": f"Simulation stopped for map {map_id}"}
    ), 200


@app.route("/api/maps/<int:map_id>/simulation_status", methods=["GET"])
def simulation_status(map_id):
    """获取指定地图的模拟状态"""
    is_running = ticker_instance.is_simulation_running(map_id)
    # 可以添加获取当前 tick 数等信息的逻辑
    current_tick = ticker_instance.active_maps.get(map_id, -1) if is_running else -1
    return jsonify(
        {"map_id": map_id, "is_running": is_running, "current_tick": current_tick}
    ), 200


# --- 修改开始：调试统计接口 ---
@app.route("/api/debug/map_stats/<int:map_id>", methods=["GET"])
def debug_map_stats(map_id):
    """临时调试接口：返回地图统计数据 (适配 3-bit 打包数据)"""
    map_data_row = database.get_map_by_id(map_id)
    if not map_data_row:
        return jsonify({"error": "Map not found"}), 404

    width, height, packed_map_bytes = map_data_row

    # --- 修改：解包 3-bit 数据来统计 ---
    stats = {
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
    }  # 初始化所有可能的 3-bit 值 (0-7)

    total_tiles = width * height
    # 遍历打包的数据并解包计数
    for i in range(total_tiles):
        byte_index = (i * 3) // 8
        bit_offset = (i * 3) % 8

        if byte_index >= len(packed_map_bytes):
            # 数据不完整或越界
            print(
                f"Warning: Incomplete packed data for map {map_id} while calculating stats."
            )
            break

        if bit_offset > 5:  # 跨越两个字节 (假设使用之前讨论的打包方式)
            # 处理跨字节的情况
            bits_in_first_byte = 8 - bit_offset
            bits_in_second_byte = 3 - bits_in_first_byte
            # 确保不越界
            if byte_index + 1 < len(packed_map_bytes):
                part1 = (packed_map_bytes[byte_index] >> bit_offset) & (
                    (1 << bits_in_first_byte) - 1
                )
                part2 = (
                    packed_map_bytes[byte_index + 1] & ((1 << bits_in_second_byte) - 1)
                ) << bits_in_first_byte
                tile_value = part1 | part2
            else:
                # 如果第二个字节不存在，则只取第一个字节的部分（可能导致数据不准确）
                part1 = (packed_map_bytes[byte_index] >> bit_offset) & (
                    (1 << bits_in_first_byte) - 1
                )
                tile_value = part1
        else:
            # 在一个字节内
            mask = (1 << 3) - 1  # 0b111
            tile_value = (packed_map_bytes[byte_index] >> bit_offset) & mask

        # 只统计有效的地形值 (0-4)
        if tile_value in stats:
            stats[tile_value] += 1
        else:
            # 可选：记录无效值
            print(
                f"Warning: Found unexpected tile value {tile_value} at index {i} in map {map_id}"
            )

    # --- 修改结束 ---
    return jsonify(
        {
            "map_id": map_id,
            "width": width,
            "height": height,
            # "total_tiles": len(map_bytes), # 原来的 len(map_bytes) 不再是 tile 数量
            "total_tiles": total_tiles,  # 使用计算出的总 tile 数
            "stats": stats,
            "readable_stats": {
                "PLAIN (0)": stats.get(0, 0),
                "FOREST (1)": stats.get(1, 0),
                "WATER (2)": stats.get(2, 0),
                "FARM_UNTILLED (3)": stats.get(3, 0),
                "FARM_TILLED (4)": stats.get(4, 0),
                # 可以包含 5, 6, 7 如果想看是否有无效数据
            },
        }
    )


# --- 修改结束 ---

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=16151, debug=True)
