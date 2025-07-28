# core/database.py
import os
import sqlite3
import json
from contextlib import closing
import logging
from typing import Optional, List, Dict, Tuple, Any

# --- 定义自定义异常 ---
class DatabaseError(Exception):
    """数据库操作相关的基础异常"""
    pass

class MapNotFoundError(DatabaseError):
    """找不到指定地图的异常"""
    pass

class InvalidInputError(DatabaseError):
    """输入参数无效的异常"""
    pass

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'database')
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'world_maps.db')

def get_connection():
    """获取数据库连接，并启用外键约束"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """初始化数据库，创建或更新所需表格"""
    with get_connection() as conn:
        # --- World Maps 表 (无改动) ---
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
        
        # --- Houses 表 (重构) ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            x INTEGER, -- 真实房屋的坐标，虚拟房屋为 NULL
            y INTEGER, -- 真实房屋的坐标，虚拟房屋为 NULL
            capacity INTEGER NOT NULL DEFAULT 1, -- 真实房屋为4，虚拟房屋为1
            integrity INTEGER, -- 真实房屋的完好度，虚拟房屋为 NULL
            storage TEXT, -- 存储仓库物品的 JSON 字符串
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE
        )
        ''')

        # --- Villagers 表 (重构) ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS villagers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            house_id INTEGER NOT NULL,
            name TEXT,
            gender TEXT NOT NULL CHECK(gender IN ('male', 'female')),
            age_in_ticks INTEGER NOT NULL DEFAULT 0,
            hunger INTEGER NOT NULL DEFAULT 100,
            status TEXT DEFAULT 'idle',
            current_task TEXT,
            task_progress INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE,
            -- 使用 RESTRICT 防止意外删除有居民的房屋
            FOREIGN KEY (house_id) REFERENCES houses (id) ON DELETE RESTRICT 
        )
        ''')

        # --- Events 表 (为增量更新新增) ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            tick INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL, -- 存储事件具体内容的 JSON
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_events_map_tick ON events (map_id, tick);')
        
        conn.commit()

# --- World Maps 表操作函数 ---
def insert_map(name: str, width: int, height: int, map_bytes: bytes) -> Optional[int]:
    """
    插入一张新地图到数据库。
    Args:
        name: 地图名称。
        width: 地图宽度。
        height: 地图高度。
        map_bytes: 地图的 3-bit 打包数据。
    Returns:
        Optional[int]: 新插入地图的 ID。
    Raises:
        DatabaseError: 如果插入地图失败。
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO world_maps (name, width, height, map_data) VALUES (?, ?, ?, ?)",
                    (name, width, height, map_bytes)
                )
                map_id = cursor.lastrowid
                if map_id is not None:
                    logger.info(f"Database: Inserted new map '{name}' with ID {map_id}")
                    return map_id
                # 正常插入后 lastrowid 不应为 None，如果为 None 则说明有问题
                raise DatabaseError(f"Failed to retrieve lastrowid for map '{name}' after insertion.")
    except Exception as e:
        logger.error(f"Database: Failed to insert map '{name}': {e}")
        raise DatabaseError(f"Failed to insert map '{name}'") from e

def get_maps_list() -> List[Tuple[int, str, int, int, Any]]:
    """
    获取所有地图的列表（不包含地图数据本身）。
    Returns:
        list: 包含地图信息元组的列表 [(id, name, width, height, created_at), ...]。
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC")
        maps = cursor.fetchall()
        logger.debug(f"Database: Fetched list of {len(maps)} maps")
        return maps

def get_map_by_id(map_id: int) -> Optional[Tuple[int, int, bytes]]:
    """
    根据 ID 获取地图的元数据和数据。
    Args:
        map_id: 地图 ID。
    Returns:
        tuple or None: (width, height, map_data) 或 None (如果未找到)。
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,))
        row = cursor.fetchone()
        if row:
            logger.debug(f"Database: Retrieved map data for ID {map_id}")
        else:
            logger.warning(f"Database: Map with ID {map_id} not found")
        return row

def update_map_data(map_id: int, map_bytes: bytes) -> bool:
    """
    更新指定地图的 map_data 字段。
    Args:
        map_id: 地图 ID。
        map_bytes: 新的地图 3-bit 打包数据。
    Returns:
        bool: 是否更新成功。
    """
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

                # 可选：获取地图名用于日志
                name_row = conn.execute(
                    "SELECT name FROM world_maps WHERE id = ?", (map_id,)
                ).fetchone()
                map_name = name_row[0] if name_row else "未知地图名"
                logger.info(f"成功更新地图ID {map_id} ({map_name})，数据大小：{len(map_bytes)} 字节。")
                return True
    except Exception as e:
        logger.error(f"更新地图数据时发生异常，地图ID {map_id}，错误信息：{e}")
        return False

def delete_map(map_id: int) -> bool:
    """
    根据 ID 删除地图。
    Args:
        map_id: 地图 ID。
    Returns:
        bool: 是否删除成功。
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM world_maps WHERE id=?", (map_id,))
                if cursor.rowcount > 0:
                    logger.info(f"Database: Deleted map with ID {map_id}")
                    return True
                else:
                    logger.warning(f"Database: Attempted to delete map ID {map_id}, but it was not found.")
                    return False
    except Exception as e:
        logger.error(f"删除地图时发生异常，地图ID {map_id}，错误信息：{e}")
        return False

# --- Houses 表操作函数 (全新/重构) ---

def create_virtual_house(map_id: int, initial_storage: Optional[Dict[str, Any]] = None) -> Optional[int]:
    storage_json = json.dumps(initial_storage or {})
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO houses (map_id, capacity, storage) VALUES (?, 1, ?)",
                    (map_id, storage_json)
                )
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to create virtual house for map {map_id}: {e}")
        return None

def upgrade_house_to_real(house_id: int, x: int, y: int) -> bool:
    """将一个虚拟房屋升级为坐标确定的真实房屋"""
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    "UPDATE houses SET x=?, y=?, capacity=4, integrity=100 WHERE id=?",
                    (x, y, house_id)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to upgrade house {house_id} to real: {e}")
        return False

def get_house_by_id(house_id: int) -> Optional[Dict[str, Any]]:
    """根据ID获取单个房屋的详细信息"""
    try:
        with closing(get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM houses WHERE id=?", (house_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching house {house_id}: {e}")
        return None

def update_house_storage(house_id: int, new_storage: Dict[str, Any]) -> bool:
    """更新指定房屋的仓库"""
    storage_json = json.dumps(new_storage)
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    "UPDATE houses SET storage=? WHERE id=?", (storage_json, house_id)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to update storage for house {house_id}: {e}")
        return False
        
def delete_house(house_id: int) -> bool:
    """删除一个房屋记录（通常在确认所有居民已搬离后调用）"""
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM houses WHERE id=?", (house_id,))
                return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        logger.error(f"Attempted to delete house {house_id} which may still have villagers.")
        return False
    except Exception as e:
        logger.error(f"Failed to delete house {house_id}: {e}")
        return False

# --- Villagers 表操作函数 (全新/重构) ---

def insert_villager(map_id: int, house_id: int, name: str, gender: str) -> Optional[int]:
    """插入一个拥有基本信息的新村民"""
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO villagers (map_id, house_id, name, gender)
                    VALUES (?, ?, ?, ?)
                    """,
                    (map_id, house_id, name, gender)
                )
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to insert villager into house {house_id}: {e}")
        return None

def get_villagers_by_map_id(map_id: int) -> List[Dict[str, Any]]:
    """获取指定地图上的所有村民信息"""
    try:
        with closing(get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM villagers WHERE map_id=?", (map_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching villagers for map {map_id}: {e}")
        return []

def update_villagers(map_id: int, villagers_data: List[Dict[str, Any]]):
    """批量更新村民的状态，性能更高"""
    update_tuples = [
        (
            v['age_in_ticks'], v['hunger'], v['status'], v['current_task'],
            v['task_progress'], v['house_id'], v['id']
        )
        for v in villagers_data
    ]
    try:
        with closing(get_connection()) as conn:
            with conn:
                conn.executemany(
                    """
                    UPDATE villagers SET
                    age_in_ticks=?, hunger=?, status=?, current_task=?,
                    task_progress=?, house_id=?
                    WHERE id=?
                    """,
                    update_tuples
                )
    except Exception as e:
        logger.error(f"Failed to bulk update villagers for map {map_id}: {e}")
        
def delete_villager(villager_id: int) -> bool:
    """删除一个村民（例如，当他们死亡时）"""
    try:
        with closing(get_connection()) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM villagers WHERE id=?", (villager_id,))
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to delete villager {villager_id}: {e}")
        return False

# --- Event Log 函数 (为增量更新新增) ---

def log_event(map_id: int, tick: int, event_type: str, payload: Dict[str, Any]):
    """记录一个游戏事件，用于增量更新"""
    payload_json = json.dumps(payload)
    try:
        with closing(get_connection()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO events (map_id, tick, event_type, payload) VALUES (?, ?, ?, ?)",
                    (map_id, tick, event_type, payload_json)
                )
    except Exception as e:
        logger.error(f"Failed to log event for map {map_id}: {e}")

def get_events_since_tick(map_id: int, since_tick: int) -> List[Dict[str, Any]]:
    """获取指定tick之后的所有事件"""
    try:
        with closing(get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT tick, event_type, payload FROM events WHERE map_id=? AND tick > ? ORDER BY tick",
                (map_id, since_tick)
            )
            events = []
            for row in cursor.fetchall():
                event = dict(row)
                event['payload'] = json.loads(event['payload']) # 解码JSON
                events.append(event)
            return events
    except Exception as e:
        logger.error(f"Error fetching events for map {map_id} since tick {since_tick}: {e}")
        return []