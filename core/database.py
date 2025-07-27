# core/database.py
import os
import sqlite3
from contextlib import closing
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')


BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # core目录
DATA_DIR = os.path.join(BASE_DIR, '..', 'database')
os.makedirs(DATA_DIR, exist_ok=True)  # 确保目录存在

DB_PATH = os.path.join(DATA_DIR, 'world_maps.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS world_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            map_data BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()

def insert_map(name: str, width: int, height: int, map_bytes: bytes):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            cursor = conn.execute(
                "INSERT INTO world_maps (name, width, height, map_data) VALUES (?, ?, ?, ?)",
                (name, width, height, map_bytes)
            )
            map_id = cursor.lastrowid
            print(f"Database: Inserted new map '{name}' with ID {map_id}") # 添加打印
            return map_id # 返回 ID

def get_maps_list():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC")
        maps = cursor.fetchall()
        print(f"Database: Fetched list of {len(maps)} maps") # 添加打印
        return maps

def get_map_by_id(map_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,))
        row = cursor.fetchone()
        if row:
            print(f"Database: Retrieved map data for ID {map_id}") # 添加打印
        else:
            print(f"Database: Map with ID {map_id} not found") # 添加打印
        return row

def update_map_data(map_id: int, map_bytes: bytes) -> bool:
    """更新指定地图的 map_data 字段，写入整个数据块"""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                cursor = conn.execute(
                    "UPDATE world_maps SET map_data = ? WHERE id = ?",
                    (map_bytes, map_id)
                )
                if cursor.rowcount == 0:
                    logger.warning(f"数据库更新失败：地图ID {map_id} 不存在。")
                    return False

                # 尽量减少查询次数，合并查询名称
                name_row = conn.execute(
                    "SELECT name FROM world_maps WHERE id = ?", (map_id,)
                ).fetchone()
                map_name = name_row[0] if name_row else "未知地图名"
                logger.info(f"成功更新地图ID {map_id} ({map_name})，数据大小：{len(map_bytes)} 字节。")
                return True
    except Exception as e:
        logger.error(f"更新地图数据时发生异常，地图ID {map_id}，错误信息：{e}")
        return False


def update_tile(map_id: int, x: int, y: int, new_tile_value: int) -> bool:
    """
    只修改指定格子的瓦片值，效率比重写整个二维转换更高
    """
    row = get_map_by_id(map_id)
    if not row:
        logger.error(f"地图ID {map_id} 不存在，无法更新瓦片。")
        return False

    width, height, map_bytes = row

    if not (0 <= x < width and 0 <= y < height):
        logger.warning(f"更新瓦片失败：坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")
        return False

    try:
        tiles = bytearray(map_bytes)  # 用bytearray便于修改单个字节
        index = y * width + x
        tiles[index] = new_tile_value

        return update_map_data(map_id, bytes(tiles))
    except Exception as e:
        logger.error(f"修改瓦片异常，地图ID {map_id}，坐标({x}, {y})，错误：{e}")
        return False
