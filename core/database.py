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
    """获取数据库连接，并启用外键约束"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
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
    """初始化数据库。此函数创建所有表结构。"""
    with _get_connection() as conn:
        # --- World Maps 表 ---
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
        
        # --- Houses 表 ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            x INTEGER,
            y INTEGER,
            capacity INTEGER NOT NULL DEFAULT 4,
            current_occupants TEXT, -- JSON array of villager IDs
            food_storage INTEGER DEFAULT 0,
            wood_storage INTEGER DEFAULT 0,
            seeds_storage INTEGER DEFAULT 0,
            build_tick INTEGER DEFAULT 0,
            is_standing BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE
        )
        ''')
        
        # --- Villagers 表---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS villagers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            gender TEXT NOT NULL CHECK(gender IN ('male', 'female')),
            age INTEGER NOT NULL DEFAULT 20, -- 年龄（岁）
            age_in_ticks INTEGER NOT NULL DEFAULT 0, -- 年龄（tick）
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            house_id INTEGER, -- 可以为NULL，表示无家可归
            hunger INTEGER NOT NULL DEFAULT 100,
            food INTEGER DEFAULT 0,
            wood INTEGER DEFAULT 0,
            seeds INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle',
            current_task TEXT, -- 例如: 'build_farmland:10,20'
            task_progress INTEGER DEFAULT 0,
            last_reproduction_tick INTEGER DEFAULT 0,
            is_alive BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE,
            FOREIGN KEY (house_id) REFERENCES houses (id) ON DELETE SET NULL
        )
        ''')

        # --- Events 表 ---
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
    """
    【统一读取接口】
    获取一个完整的世界状态快照，包含解包后的地形和所有实体。
    """
    try:
        with closing(_get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            
            # 1. 获取地图 BLOB 和元数据
            map_row = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,)).fetchone()
            if not map_row: return None
            width, height, map_blob = map_row

            # 2. 获取实体
            villagers = [dict(row) for row in conn.execute("SELECT * FROM villagers WHERE map_id=? AND is_alive=1", (map_id,)).fetchall()]
            houses_rows = conn.execute("SELECT * FROM houses WHERE map_id=? AND is_standing=1", (map_id,)).fetchall()
            
            # 3. 处理数据格式
            grid_2d = _unpack_3bit_bytes(map_blob, width, height)
            houses = []
            for row in houses_rows:
                house = dict(row)
                # 解析JSON字段
                house['current_occupants'] = json.loads(house.get('current_occupants') or '[]')
                houses.append(house)

            return WorldSnapshot(map_id, width, height, grid_2d, villagers, houses)
            
    except Exception as e:
        logger.error(f"Failed to get world snapshot for map {map_id}: {e}", exc_info=True)
        return None

def commit_changes(map_id: int, changeset: Dict[str, List[Any]]):
    """
    【统一写入接口】
    以事务方式，将一个包含所有变更的集合提交到数据库。
    'changeset' 字典结构:
    {
        "tile_changes": [(x, y, new_type), ...],
        "villager_updates": [villager_dict, ...],
        "house_updates": [house_dict, ...],
        "new_villagers": [villager_dict, ...],
        "new_houses": [house_dict, ...],
        "deleted_villager_ids": [id, ...],
        "deleted_house_ids": [id, ...]
    }
    """
    try:
        with closing(_get_connection()) as conn:
            # with conn 自动开始一个事务。如果任何步骤失败，所有更改都将回滚。
            with conn:
                # --- 1. 处理创建 (Creation) ---
                # 先创建新的实体，这样它们就可以在同一个tick中被更新
                
                new_houses = changeset.get("new_houses")
                if new_houses:
                    house_tuples = [
                        (map_id, h.x, h.y, h.capacity, json.dumps(h.current_occupants), 
                         h.food_storage, h.wood_storage, h.seeds_storage, h.build_tick, h.is_standing)
                        for h in new_houses
                    ]
                    conn.executemany(
                        "INSERT INTO houses (map_id, x, y, capacity, current_occupants, food_storage, wood_storage, seeds_storage, build_tick, is_standing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        house_tuples
                    )

                new_villagers = changeset.get("new_villagers")
                if new_villagers:
                    villager_tuples = [
                        (map_id, v.name, v.gender, v.age, v.age_in_ticks, v.x, v.y, v.house_id,
                         v.hunger, v.food, v.wood, v.seeds, v.status.value, v.current_task,
                         v.task_progress, v.last_reproduction_tick, v.is_alive)
                        for v in new_villagers
                    ]
                    conn.executemany(
                        "INSERT INTO villagers (map_id, name, gender, age, age_in_ticks, x, y, house_id, hunger, food, wood, seeds, status, current_task, task_progress, last_reproduction_tick, is_alive) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        villager_tuples
                    )

                # --- 2. 处理更新 (Updates) ---
                
                # 地形变更
                tile_changes = changeset.get("tile_changes")
                if tile_changes:
                    map_row = conn.execute("SELECT width, map_data FROM world_maps WHERE id=?", (map_id,)).fetchone()
                    if map_row:
                        width, map_blob = map_row
                        map_bytearray = bytearray(map_blob)
                        for x, y, new_type in tile_changes:
                            _write_tile_to_blob(map_bytearray, x, y, new_type, width)
                        conn.execute("UPDATE world_maps SET map_data=? WHERE id=?", (bytes(map_bytearray), map_id))

                # 村民状态更新
                villager_updates = changeset.get("villager_updates")
                if villager_updates:
                    update_tuples = [
                        (v.age, v.age_in_ticks, v.x, v.y, v.house_id, v.hunger, v.food, v.wood, v.seeds,
                         v.status.value, v.current_task, v.task_progress, v.last_reproduction_tick, v.is_alive, v.id) 
                        for v in villager_updates
                    ]
                    conn.executemany(
                        "UPDATE villagers SET age=?, age_in_ticks=?, x=?, y=?, house_id=?, hunger=?, food=?, wood=?, seeds=?, status=?, current_task=?, task_progress=?, last_reproduction_tick=?, is_alive=? WHERE id=?",
                        update_tuples
                    )

                # 房屋状态更新
                house_updates = changeset.get("house_updates")
                if house_updates:
                    update_tuples = [
                        (json.dumps(h.current_occupants), h.food_storage, h.wood_storage, h.seeds_storage, h.is_standing, h.id) 
                        for h in house_updates
                    ]
                    conn.executemany(
                        "UPDATE houses SET current_occupants=?, food_storage=?, wood_storage=?, seeds_storage=?, is_standing=? WHERE id=?",
                        update_tuples
                    )
                
                # --- 3. 处理删除 (Deletion) ---
                # 最后执行删除，以避免外键约束问题
                
                deleted_house_ids = changeset.get("deleted_house_ids")
                if deleted_house_ids:
                    # 注意：由于村民表有外键约束，删除房屋前必须先确保房屋是空的
                    conn.executemany("DELETE FROM houses WHERE id=?", [(hid,) for hid in deleted_house_ids])

                deleted_villager_ids = changeset.get("deleted_villager_ids")
                if deleted_villager_ids:
                    conn.executemany("DELETE FROM villagers WHERE id=?", [(vid,) for vid in deleted_villager_ids])

    except sqlite3.IntegrityError as e:
        logger.error(f"Database Integrity Error during commit for map {map_id}: {e}. Changes will be rolled back.")
        raise # 重新抛出，让上层知道事务失败

    except Exception as e:
        logger.error(f"Failed to commit changeset for map {map_id}: {e}", exc_info=True)
        raise # 重新抛出异常，让上层知道事务失败

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

# --- 事件日志函数---

def log_event(map_id: int, tick: int, event_type: str, payload: Dict[str, Any]):
    """
    记录一个游戏事件，用于增量更新。
    此函数被设计为"即发即忘"，即使失败也不应中断主更新循环，
    但会记录错误。
    """
    payload_json = json.dumps(payload)
    try:
        # 注意：这里我们为事件日志使用一个独立的连接，
        # 以确保它在主事务之外，或者如果需要也可以包含在内。
        # 简单起见，我们使用独立连接。
        with closing(_get_connection()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO events (map_id, tick, event_type, payload) VALUES (?, ?, ?, ?)",
                    (map_id, tick, event_type, payload_json)
                )
    except Exception as e:
        # 日志记录失败不应该使整个Tick失败，但需要被知晓
        logger.warning(f"Failed to log event for map {map_id} at tick {tick}: {e}")


def get_events_since_tick(map_id: int, since_tick: int) -> List[Dict[str, Any]]:
    """
    【API调用】获取指定tick之后的所有事件。
    这是提供给客户端API用于高效刷新的接口。
    """
    try:
        with closing(_get_connection()) as conn:
            # 使用 sqlite3.Row 工厂可以让我们像访问字典一样访问列
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT tick, event_type, payload FROM events WHERE map_id=? AND tick > ? ORDER BY tick",
                (map_id, since_tick)
            )
            
            events = []
            for row in cursor.fetchall():
                # 将数据库行转换为字典
                event = dict(row)
                # 将存储为JSON字符串的payload解码回Python字典
                event['payload'] = json.loads(event['payload'])
                events.append(event)
            return events
            
    except Exception as e:
        logger.error(f"Error fetching events for map {map_id} since tick {since_tick}: {e}")
        # 在发生任何错误时，安全地返回一个空列表
        return []