from flask import Flask, request, jsonify, render_template
from core.config import Config
from core.world import generate_tiles
from core import database

app = Flask(__name__)

config = Config()
database.init_db()  # 这行现在会真正初始化数据库表

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'world': config.get_world(),
        'forest': config.get_forest(),
        'water': config.get_water(),
        'view': config.get_view()
    })

@app.route('/api/maps/<int:map_id>', methods=['GET'])
def get_map(map_id):
    with database.get_connection() as conn:
        cursor = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Map not found"}), 404
        
        width, height, map_bytes = row
        tiles = list(map_bytes)
        tiles_2d = [tiles[i*width:(i+1)*width] for i in range(height)]
        return jsonify({
            "id": map_id,
            "width": width,
            "height": height,
            "tiles": tiles_2d
        })

@app.route('/api/maps', methods=['GET'])
def get_maps():
    with database.get_connection() as conn:
        cursor = conn.execute("SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC")
        maps = [
            {"id": row[0], "name": row[1], "width": row[2], "height": row[3], "created_at": row[4]}
            for row in cursor.fetchall()
        ]
    return jsonify(maps)

@app.route('/api/generate_map', methods=['POST'])
def generate_map():
    data = request.json or {}

    # 基本校验
    try:
        name = data['name']
        world_params = data['world']
        forest_params = data['forest']
        water_params = data['water']
    except KeyError as e:
        return jsonify({'error': f'Missing required parameter: {str(e)}'}), 400

    try:
        width = int(world_params['width'])
        height = int(world_params['height'])

        # 生成地图
        tiles = generate_tiles(
            width=width,
            height=height,
            seed_prob=forest_params['seed_prob'],
            forest_iterations=forest_params['iterations'],
            forest_birth_threshold=forest_params['birth_threshold'],
            water_density=water_params['density'],
            water_turn_prob=water_params['turn_prob'],
            water_stop_prob=water_params['stop_prob'],
            water_height_influence=water_params['height_influence']
        )
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid or missing map generation parameter: {str(e)}'}), 400

    # 转成bytes写入数据库
    raw_bytes = bytes([tile for row in tiles for tile in row])
    map_id = database.insert_map(name, width, height, raw_bytes)

    return jsonify({
        'success': True,
        'map_id': map_id,
        'name': name,
        'tiles': tiles,
        'used_params': {
            'world': world_params,
            'forest': forest_params,
            'water': water_params
        }
    })

@app.route('/api/maps/<int:map_id>', methods=['DELETE'])
def delete_map(map_id):
    with database.get_connection() as conn:
        conn.execute("DELETE FROM world_maps WHERE id=?", (map_id,))
        conn.commit()
    return jsonify({"success": True})

@app.route('/view_map/<int:map_id>')
def view_map(map_id):
    return render_template('map.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=16151, debug=True)
