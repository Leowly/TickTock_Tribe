# core/database.py
import os
import sqlite3
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
# 注意：logging.basicConfig 通常在应用入口 (app.py) 设置一次即可
# logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # core目录
DATA_DIR = os.path.join(BASE_DIR, '..', 'database')
os.makedirs(DATA_DIR, exist_ok=True)  # 确保目录存在

DB_PATH = os.path.join(DATA_DIR, 'world_maps.db')

def get_connection():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

def init_db():
    """初始化数据库，创建所需表格"""
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
        # --- Houses 表 ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (map_id) REFERENCES world_maps (id) ON DELETE CASCADE
        )
        ''')
        # --- Villagers 表 ---
        conn.execute('''
        CREATE TABLE IF NOT EXISTS villagers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            house_id INTEGER,
            name TEXT,
            status TEXT DEFAULT 'idle',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (house_id) REFERENCES houses (id) ON DELETE SET NULL
        )
        ''')
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

# --- Houses 表操作函数 ---
def insert_house(map_id: int, x: int, y: int, capacity: int) -> Optional[int]:
    """
    在指定地图上插入一个新房子。
    Args:
        map_id: 所属地图ID。
        x: 房子x坐标。
        y: 房子y坐标。
        capacity: 房子容量 (1-4)。
    Returns:
        Optional[int]: 新插入房子的 ID。
    Raises:
        InvalidInputError: 如果 capacity 无效。
        DatabaseError: 如果数据库插入失败（如外键约束违反）。
    """
    if not (1 <= capacity <= 4):
        error_msg = f"Invalid house capacity: {capacity}. Must be between 1 and 4."
        logger.error(f"Tried to insert house with invalid capacity: {capacity}")
        raise InvalidInputError(error_msg)

    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO houses (map_id, x, y, capacity) VALUES (?, ?, ?, ?)",
                    (map_id, x, y, capacity)
                )
                house_id = cursor.lastrowid
                if house_id is not None:
                    logger.info(f"Database: Inserted new house (ID: {house_id}) on map {map_id} at ({x}, {y}) with capacity {capacity}")
                    return house_id
                raise DatabaseError(f"Failed to retrieve lastrowid for house on map {map_id}.")
    except sqlite3.IntegrityError as e:
        error_msg = f"Database constraint failed when inserting house on map {map_id} at ({x}, {y}): {e}"
        logger.error(error_msg)
        raise DatabaseError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error inserting house on map {map_id} at ({x}, {y}): {e}"
        logger.error(error_msg)
        raise DatabaseError(error_msg) from e

def get_houses_by_map_id(map_id: int) -> List[Dict[str, Any]]:
    """
    获取指定地图上的所有房子信息。
    Args:
        map_id: 地图 ID。
    Returns:
        List[Dict]: 包含房子信息的字典列表。
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, map_id, x, y, capacity FROM houses WHERE map_id = ? ORDER BY created_at", (map_id,))
            rows = cursor.fetchall()
            houses = [dict(row) for row in rows]
            logger.debug(f"Database: Retrieved {len(houses)} houses for map {map_id}")
            return houses
    except Exception as e:
        error_msg = f"Error retrieving houses for map {map_id}: {e}"
        logger.error(error_msg)
        return []

# --- Villagers 表操作函数 ---
def insert_villager(house_id: int, name: Optional[str] = None) -> Optional[int]:
    """
    为指定房子添加一个居民。
    Args:
        house_id: 所属房子ID。
        name: 居民名字 (可选)。
    Returns:
        Optional[int]: 新插入居民的 ID。
    Raises:
        DatabaseError: 如果数据库插入失败（如外键约束违反）。
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO villagers (house_id, name) VALUES (?, ?)",
                    (house_id, name)
                )
                villager_id = cursor.lastrowid
                if villager_id is not None:
                    logger.info(f"Database: Inserted new villager (ID: {villager_id}) into house {house_id}" + (f" named {name}" if name else " (unnamed)"))
                    return villager_id
                raise DatabaseError(f"Failed to retrieve lastrowid for villager in house {house_id}.")
    except sqlite3.IntegrityError as e:
        error_msg = f"Database constraint failed when inserting villager into house {house_id}: {e}"
        logger.error(error_msg)
        raise DatabaseError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error inserting villager into house {house_id}: {e}"
        logger.error(error_msg)
        raise DatabaseError(error_msg) from e

def get_villagers_by_house_id(house_id: int) -> List[Dict[str, Any]]:
    """
    获取指定房子内的所有居民。
    Args:
        house_id: 房子 ID。
    Returns:
        List[Dict]: 包含居民信息的字典列表。
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, house_id, name, status FROM villagers WHERE house_id = ?", (house_id,))
            rows = cursor.fetchall()
            villagers = [dict(row) for row in rows]
            logger.debug(f"Database: Retrieved {len(villagers)} villagers for house {house_id}")
            return villagers
    except Exception as e:
        error_msg = f"Error retrieving villagers for house {house_id}: {e}"
        logger.error(error_msg)
        return []

# 注意：get_villagers_by_map_id 可能也需要，如果想获取地图上所有居民
# def get_villagers_by_map_id(map_id: int) -> List[Dict[str, Any]]:
#     """获取指定地图上的所有居民（通过关联的房子）"""
#     try:
#         with closing(sqlite3.connect(DB_PATH)) as conn:
#             conn.row_factory = sqlite3.Row
#             # 使用 JOIN 查询关联 houses 表
#             cursor = conn.execute("""
#                 SELECT v.id, v.house_id, v.name, v.status
#                 FROM villagers v
#                 JOIN houses h ON v.house_id = h.id
#                 WHERE h.map_id = ?
#             """, (map_id,))
#             rows = cursor.fetchall()
#             villagers = [dict(row) for row in rows]
#             logger.debug(f"Database: Retrieved {len(villagers)} villagers for map {map_id}")
#             return villagers
#     except Exception as e:
#         error_msg = f"Error retrieving villagers for map {map_id}: {e}"
#         logger.error(error_msg)
#         return []