# core/database.py
import os
import sqlite3
from contextlib import closing

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
    """更新指定地图的 map_data 字段"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            cursor = conn.execute(
                "UPDATE world_maps SET map_data = ? WHERE id = ?",
                (map_bytes, map_id)
            )
            success = cursor.rowcount > 0 # 检查是否更新成功
            if success:
                # --- 添加打印：显示更新了哪个地图 ---
                # 可选：获取地图名称用于打印
                name_cursor = conn.execute("SELECT name FROM world_maps WHERE id = ?", (map_id,))
                map_name = name_cursor.fetchone()
                map_name_str = f"'{map_name[0]}'" if map_name else "Unknown"
                print(f"Database: Updated map data for map ID {map_id} ({map_name_str}), {len(map_bytes)} bytes written.")
                # --- 打印结束 ---
            else:
                print(f"Database: No rows updated for map ID {map_id}. Map might not exist.")
            return success # 返回是否更新成功

# 注意：为了保持与之前讨论的一致性，如果你在 world_updater.py 中使用了 logger，
# 建议也在这里添加 logger 的初始化和使用，而不是仅仅使用 print。
# 但在你当前的代码库中，database.py 主要使用 print，所以这里也保持一致。
# 如果你想用 logger，请参考之前回复中的建议。