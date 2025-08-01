# core/database.py
import os
import sqlite3
import json
from contextlib import closing
import logging
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass

# --- 异常类定义 ---
class DatabaseError(Exception):
    """数据库操作相关的基础异常"""
    pass

class MapNotFoundError(DatabaseError):
    """找不到指定地图的异常"""
    pass

class InvalidInputError(DatabaseError):
    """输入参数无效的异常"""
    pass


# --- 数据类定义 ---
@dataclass
class WorldSnapshot:
    """封装了一个tick开始时世界状态的完整快照，供WorldUpdater使用。"""
    map_id: int
    width: int
    height: int
    grid_2d: List[List[int]]
    villagers: List[Dict[str, Any]]
    houses: List[Dict[str, Any]]

# --- 模块设置 ---
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'database')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'world_maps.db')

# --- 内部辅助函数 ---
def _get_connection():
    """获取数据库连接，并启用外键约束和WAL模式以支持高并发。"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def _unpack_3bit_bytes(packed_bytes: bytes, width: int, height: int) -> List[List[int]]:
    """将3-bit打包的BLOB解包成二维列表。"""
    if not packed_bytes: return [[0] * width for _ in range(height)]
    grid = [[0] * width for _ in range(height)]
    for i in range(width * height):
        byte_idx, bit_offset = divmod(i * 3, 8)
        if byte_idx >= len(packed_bytes): break
        y, x = divmod(i, width)
        if bit_offset <= 5:
            grid[y][x] = (packed_bytes[byte_idx] >> (5 - bit_offset)) & 0b111
        else:
            b1 = packed_bytes[byte_idx]
            b2 = packed_bytes[byte_idx + 1] if byte_idx + 1 < len(packed_bytes) else 0
            bits_in_b1 = 8 - bit_offset
            val = ((b1 & ((1 << bits_in_b1) - 1)) << (3 - bits_in_b1)) | (b2 >> (8 - (3 - bits_in_b1)))
            grid[y][x] = val
    return grid

def _write_tile_to_blob(packed_data: bytearray, x: int, y: int, value: int, width: int):
    """向给定的bytearray中精确写入单个瓦片的值。"""
    i = y * width + x
    byte_idx, bit_offset = divmod(i * 3, 8)
    if byte_idx >= len(packed_data): return
    if bit_offset <= 5:
        mask = ~(0b111 << (5 - bit_offset))
        packed_data[byte_idx] = (packed_data[byte_idx] & mask) | (value << (5 - bit_offset))
    else:
        bits_in_b1 = 8 - bit_offset
        mask1 = ~((1 << bits_in_b1) - 1)
        packed_data[byte_idx] = (packed_data[byte_idx] & mask1) | (value >> (3 - bits_in_b1))
        if byte_idx + 1 < len(packed_data):
            mask2 = ~(((1 << (3 - bits_in_b1)) - 1) << (8 - (3 - bits_in_b1)))
            packed_data[byte_idx + 1] = (packed_data[byte_idx + 1] & mask2) | ((value & ((1 << (3 - bits_in_b1)) - 1)) << (8 - (3 - bits_in_b1)))

# --- 公共API ---
def init_db():
    """【新】初始化数据库。此函数创建所有表结构。"""
    with _get_connection() as conn:
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
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            x INTEGER, 
            y INTEGER,
            capacity INTEGER NOT NULL DEFAULT 999,
            current_occupants TEXT, 
            food_storage INTEGER DEFAULT 0,
            wood_storage INTEGER DEFAULT 0,
            seeds_storage INTEGER DEFAULT 0,
            build_tick INTEGER DEFAULT 0,
            is_standing BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS villagers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            gender TEXT NOT NULL CHECK(gender IN ('male', 'female')),
            age INTEGER NOT NULL DEFAULT 20, 
            age_in_ticks INTEGER NOT NULL DEFAULT 0,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            house_id INTEGER NOT NULL,
            hunger INTEGER NOT NULL DEFAULT 100,
            status TEXT DEFAULT 'idle',
            current_task TEXT,
            task_progress INTEGER DEFAULT 0,
            last_reproduction_tick INTEGER DEFAULT 0,
            is_alive BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE,
            FOREIGN KEY (house_id) REFERENCES houses (id) ON DELETE CASCADE
        )
        ''')

        conn.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            tick INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_events_map_tick ON events (map_id, tick);')
        
        conn.commit()
        logger.info("Database initialized and all tables are ensured to exist.")

def get_world_snapshot(map_id: int) -> Optional[WorldSnapshot]:
    """获取一个完整的世界状态快照，包含解包后的地形和所有实体。"""
    try:
        with closing(_get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            
            map_row = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,)).fetchone()
            if not map_row: return None
            width, height, map_blob = map_row

            villagers = [dict(row) for row in conn.execute("SELECT * FROM villagers WHERE map_id=? AND is_alive=1", (map_id,)).fetchall()]
            houses_rows = conn.execute("SELECT * FROM houses WHERE map_id=? AND is_standing=1", (map_id,)).fetchall()
            
            grid_2d = _unpack_3bit_bytes(map_blob, width, height)
            houses = []
            for row in houses_rows:
                house = dict(row)
                house['current_occupants'] = json.loads(house.get('current_occupants') or '[]')
                houses.append(house)

            return WorldSnapshot(map_id, width, height, grid_2d, villagers, houses)
            
    except Exception as e:
        logger.error(f"Failed to get world snapshot for map {map_id}: {e}", exc_info=True)
        return None

def commit_changes(map_id: int, changeset: Dict[str, List[Any]]):
    try:
        with closing(_get_connection()) as conn:
            with conn: 
                # Block 1: initial_creation_pairs (no change)
                initial_pairs = changeset.get("initial_creation_pairs", [])
                for villager_obj, house_obj in initial_pairs:
                    house_cursor = conn.execute("INSERT INTO houses (map_id, x, y, capacity, current_occupants, food_storage, wood_storage, seeds_storage, build_tick, is_standing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (map_id, house_obj.x, house_obj.y, house_obj.capacity, "[]", house_obj.food_storage, house_obj.wood_storage, house_obj.seeds_storage, house_obj.build_tick, house_obj.is_standing))
                    real_house_id = house_cursor.lastrowid
                    villager_cursor = conn.execute("INSERT INTO villagers (map_id, name, gender, age, age_in_ticks, x, y, house_id, hunger, status, current_task, task_progress, last_reproduction_tick, is_alive) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (map_id, villager_obj.name, villager_obj.gender, villager_obj.age, villager_obj.age_in_ticks, villager_obj.x, villager_obj.y, real_house_id, villager_obj.hunger, villager_obj.status.value, villager_obj.current_task, villager_obj.task_progress, villager_obj.last_reproduction_tick, villager_obj.is_alive))
                    real_villager_id = villager_cursor.lastrowid
                    conn.execute("UPDATE houses SET current_occupants=? WHERE id=?", (json.dumps([real_villager_id]), real_house_id))

                # Block 2: new_villagers (no change)
                new_villagers = changeset.get("new_villagers", [])
                for villager_obj in new_villagers:
                    villager_cursor = conn.execute("INSERT INTO villagers (map_id, name, gender, age, age_in_ticks, x, y, house_id, hunger, status, current_task, task_progress, last_reproduction_tick, is_alive) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (map_id, villager_obj.name, villager_obj.gender, villager_obj.age, villager_obj.age_in_ticks, villager_obj.x, villager_obj.y, villager_obj.house_id, villager_obj.hunger, villager_obj.status.value, villager_obj.current_task, villager_obj.task_progress, villager_obj.last_reproduction_tick, villager_obj.is_alive))
                    real_villager_id = villager_cursor.lastrowid
                    house_row = conn.execute("SELECT current_occupants FROM houses WHERE id=?", (villager_obj.house_id,)).fetchone()
                    if house_row:
                        occupants = json.loads(house_row[0])
                        if -1 in occupants: occupants.remove(-1)
                        occupants.append(real_villager_id)
                        conn.execute("UPDATE houses SET current_occupants=? WHERE id=?", (json.dumps(occupants), villager_obj.house_id))

                # Block 3: build_and_move_requests (no change)
                build_requests = changeset.get("build_and_move_requests", [])
                for villager_obj, new_house_blueprint, old_warehouse_obj in build_requests:
                    house_cursor = conn.execute("INSERT INTO houses (map_id, x, y, capacity, current_occupants, food_storage, wood_storage, seeds_storage, build_tick, is_standing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",(map_id, new_house_blueprint.x, new_house_blueprint.y, new_house_blueprint.capacity, "[]", old_warehouse_obj.food_storage, old_warehouse_obj.wood_storage, old_warehouse_obj.seeds_storage, new_house_blueprint.build_tick, new_house_blueprint.is_standing))
                    real_house_id = house_cursor.lastrowid
                    conn.execute("UPDATE villagers SET house_id=? WHERE id=?", (real_house_id, villager_obj.id))
                    conn.execute("UPDATE houses SET current_occupants=? WHERE id=?", (json.dumps([villager_obj.id]), real_house_id))
                    if old_warehouse_obj.x is None:
                        conn.execute("DELETE FROM houses WHERE id=?", (old_warehouse_obj.id,))

                # Block 4: homeless_updates (no change)
                homeless_updates = changeset.get("homeless_updates", [])
                for villager_obj, new_virtual_warehouse_obj in homeless_updates:
                    house_cursor = conn.execute("INSERT INTO houses (map_id, x, y, capacity, current_occupants, food_storage, wood_storage, seeds_storage, build_tick, is_standing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (map_id, new_virtual_warehouse_obj.x, new_virtual_warehouse_obj.y, new_virtual_warehouse_obj.capacity, "[]", 0, 0, 0, new_virtual_warehouse_obj.build_tick, new_virtual_warehouse_obj.is_standing))
                    real_house_id = house_cursor.lastrowid
                    conn.execute("UPDATE villagers SET house_id=? WHERE id=?", (real_house_id, villager_obj.id))
                    conn.execute("UPDATE houses SET current_occupants=? WHERE id=?", (json.dumps([villager_obj.id]), real_house_id))

                # NEW Block 5: move_in_requests
                move_in_requests = changeset.get("move_in_requests", [])
                for villager_obj, old_warehouse_obj, target_house_obj in move_in_requests:
                    conn.execute("UPDATE houses SET food_storage = food_storage + ?, wood_storage = wood_storage + ?, seeds_storage = seeds_storage + ? WHERE id = ?", (old_warehouse_obj.food_storage, old_warehouse_obj.wood_storage, old_warehouse_obj.seeds_storage, target_house_obj.id))
                    conn.execute("UPDATE villagers SET house_id = ? WHERE id = ?", (target_house_obj.id, villager_obj.id))
                    target_house_row = conn.execute("SELECT current_occupants FROM houses WHERE id=?", (target_house_obj.id,)).fetchone()
                    if target_house_row:
                        occupants = json.loads(target_house_row[0])
                        occupants.append(villager_obj.id)
                        conn.execute("UPDATE houses SET current_occupants = ? WHERE id = ?", (json.dumps(occupants), target_house_obj.id))
                    if old_warehouse_obj.x is None:
                        conn.execute("DELETE FROM houses WHERE id = ?", (old_warehouse_obj.id,))
                
                # Block 6: Regular updates (no change)
                tile_changes = changeset.get("tile_changes", [])
                if tile_changes:
                    map_row = conn.execute("SELECT width, map_data FROM world_maps WHERE id=?", (map_id,)).fetchone()
                    if map_row:
                        width, map_blob = map_row
                        map_bytearray = bytearray(map_blob)
                        for x, y, new_type in tile_changes:
                            _write_tile_to_blob(map_bytearray, x, y, new_type, width)
                        conn.execute("UPDATE world_maps SET map_data=? WHERE id=?", (bytes(map_bytearray), map_id))
                villager_updates = changeset.get("villager_updates", [])
                if villager_updates:
                    update_tuples = [(v.age, v.age_in_ticks, v.x, v.y, v.house_id, v.hunger, v.status.value, v.current_task, v.task_progress, v.last_reproduction_tick, v.is_alive, v.id) for v in villager_updates]
                    conn.executemany("UPDATE villagers SET age=?, age_in_ticks=?, x=?, y=?, house_id=?, hunger=?, status=?, current_task=?, task_progress=?, last_reproduction_tick=?, is_alive=? WHERE id=?", update_tuples)
                house_updates = changeset.get("house_updates", [])
                if house_updates:
                    update_tuples = [(json.dumps(h.current_occupants), h.food_storage, h.wood_storage, h.seeds_storage, h.is_standing, h.id) for h in house_updates]
                    conn.executemany("UPDATE houses SET current_occupants=?, food_storage=?, wood_storage=?, seeds_storage=?, is_standing=? WHERE id=?", update_tuples)
                
                # Block 7: Deletes (no change)
                deleted_villager_ids = changeset.get("deleted_villager_ids", [])
                if deleted_villager_ids: conn.executemany("DELETE FROM villagers WHERE id=?", [(vid,) for vid in deleted_villager_ids])
                deleted_house_ids = changeset.get("deleted_house_ids", [])
                if deleted_house_ids: conn.executemany("DELETE FROM houses WHERE id=?", [(hid,) for hid in deleted_house_ids])
                
    except sqlite3.IntegrityError as e:
        logger.error(f"Database Integrity Error during commit for map {map_id}: {e}. Changes will be rolled back.")
        raise
    except Exception as e:
        logger.error(f"Failed to commit changeset for map {map_id}: {e}", exc_info=True)
        raise

def insert_map(name: str, width: int, height: int, map_bytes: bytes) -> Optional[int]:
    """插入一张新地图到数据库。"""
    try:
        with closing(_get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO world_maps (name, width, height, map_data) VALUES (?, ?, ?, ?)",
                    (name, width, height, map_bytes)
                )
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"Database: Failed to insert map '{name}': {e}")
        raise DatabaseError(f"Failed to insert map '{name}'") from e

def get_maps_list() -> List[Tuple[int, str, int, int, Any]]:
    """获取所有地图的列表（不包含地图数据本身）。"""
    with closing(_get_connection()) as conn:
        cursor = conn.execute("SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC")
        return cursor.fetchall()

def get_map_by_id(map_id: int) -> Optional[Tuple[int, int, bytes]]:
    """根据 ID 获取地图的元数据和打包数据。"""
    with closing(_get_connection()) as conn:
        cursor = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,))
        return cursor.fetchone()

def delete_map(map_id: int) -> bool:
    """根据 ID 删除地图。"""
    try:
        with closing(_get_connection()) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM world_maps WHERE id=?", (map_id,))
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"删除地图时发生异常，地图ID {map_id}，错误信息：{e}")
        return False

def get_villager_by_id(villager_id: int) -> Optional[Dict[str, Any]]:
    """根据ID获取单个村民的详细数据。"""
    with closing(_get_connection()) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM villagers WHERE id=?", (villager_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_house_by_id(house_id: int) -> Optional[Dict[str, Any]]:
    """根据ID获取单个房屋的详细数据。"""
    with closing(_get_connection()) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM houses WHERE id=?", (house_id,))
        row = cursor.fetchone()
        if not row:
            return None
        house_data = dict(row)
        house_data['current_occupants'] = json.loads(house_data.get('current_occupants') or '[]')
        return house_data