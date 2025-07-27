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

# --- 新增：直接操作 3-bit 打包数据的函数 ---

def get_tile_packed(map_id: int, x: int, y: int, width: int, height: int, packed_map_bytes: bytes) -> int:
    """
    从 3-bit 打包的字节数据中直接读取指定坐标的瓦片值。
    为了效率，这个函数不直接查询数据库，而是需要调用者提供必要的参数。
    这避免了在循环中反复查询数据库。
    Args:
        map_id: 地图ID (仅用于日志和错误处理)。
        x: 瓦片的 x 坐标。
        y: 瓦片的 y 坐标。
        width: 地图的宽度。
        height: 地图的高度。
        packed_map_bytes: 包含 3-bit 打包数据的 bytes 对象。
    Returns:
        int: 瓦片的值 (0-7)。
    Raises:
        ValueError: 如果坐标无效。
        IndexError: 如果计算出的位索引超出 packed_map_bytes 范围（数据可能损坏）。
    """
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")

    total_tiles = width * height
    expected_packed_size = (total_tiles * 3 + 7) // 8
    if len(packed_map_bytes) != expected_packed_size:
         logger.warning(f"get_tile_packed: 数据大小 ({len(packed_map_bytes)}) 与预期 ({expected_packed_size}) 不符，地图ID {map_id}。")

    i = y * width + x  # 一维索引
    bit_index = i * 3
    byte_index = bit_index // 8
    bit_offset = bit_index % 8

    # 使用 bytearray 便于索引 (虽然 bytes 也可以)
    packed_data = packed_map_bytes

    if byte_index >= len(packed_data):
        raise IndexError(f"计算出的字节索引 {byte_index} 超出数据范围 {len(packed_data)}，地图ID {map_id}。")

    value = 0
    if bit_offset <= 5: # 完全在一个字节内或在边界上
        mask = (1 << 3) - 1 # 0b111
        value = (packed_data[byte_index] >> (8 - 3 - bit_offset)) & mask
    else: # 跨越两个字节
        bits_in_first_byte = 8 - bit_offset
        bits_in_second_byte = 3 - bits_in_first_byte
        part1 = (packed_data[byte_index] & ((1 << bits_in_first_byte) - 1)) << bits_in_second_byte
        # 检查是否有第二个字节
        if byte_index + 1 < len(packed_data):
            part2 = (packed_data[byte_index + 1] >> (8 - bits_in_second_byte)) & ((1 << bits_in_second_byte) - 1)
        else:
            part2 = 0 # 如果没有下一个字节，默认为0 (或根据需要处理边界)
            logger.debug(f"get_tile_packed: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在，地图ID {map_id}。")
        value = part1 | part2

    return value

def update_tile_packed(map_id: int, x: int, y: int, new_tile_value: int, width: int, height: int, packed_map_bytes: bytes) -> bytes:
    """
    在 3-bit 打包的字节数据中直接修改指定坐标的瓦片值，并返回更新后的 bytes。
    同样，为了效率，这个函数不直接操作数据库。
    Args:
        map_id: 地图ID (仅用于日志和错误处理)。
        x: 瓦片的 x 坐标。
        y: 瓦片的 y 坐标。
        new_tile_value: 新的瓦片值 (0-7)。
        width: 地图的宽度。
        height: 地图的高度。
        packed_map_bytes: 包含 3-bit 打包数据的原始 bytes 对象。
    Returns:
        bytes: 更新后的 3-bit 打包数据。
    Raises:
        ValueError: 如果坐标或值无效。
        IndexError: 如果计算出的位索引超出范围。
    """
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")
    if not (0 <= new_tile_value <= 7):
         logger.warning(f"update_tile_packed: 瓦片值 {new_tile_value} 超出 3-bit 范围 (0-7)，地图ID {map_id}。已截断。")
         new_tile_value = max(0, min(7, new_tile_value))

    total_tiles = width * height
    expected_packed_size = (total_tiles * 3 + 7) // 8
    if len(packed_map_bytes) != expected_packed_size:
         logger.warning(f"update_tile_packed: 数据大小 ({len(packed_map_bytes)}) 与预期 ({expected_packed_size}) 不符，地图ID {map_id}。")

    # 将 bytes 转换为 bytearray 以便修改
    packed_data = bytearray(packed_map_bytes)
    i = y * width + x # 一维索引
    bit_index = i * 3
    byte_index = bit_index // 8
    bit_offset = bit_index % 8

    if byte_index >= len(packed_data):
        raise IndexError(f"计算出的字节索引 {byte_index} 超出数据范围 {len(packed_data)}，地图ID {map_id}。")

    # 清除旧的 3 位值
    if bit_offset <= 5: # 完全在一个字节内或在边界上
        mask = (1 << 3) - 1 # 0b111
        shift = 8 - 3 - bit_offset
        packed_data[byte_index] &= ~(mask << shift) # 清零对应位
        packed_data[byte_index] |= (new_tile_value << shift) & 0xFF # 设置新值
    else: # 跨越两个字节
        bits_in_first_byte = 8 - bit_offset
        bits_in_second_byte = 3 - bits_in_first_byte
        mask1 = (1 << bits_in_first_byte) - 1
        mask2 = (1 << bits_in_second_byte) - 1
        packed_data[byte_index] &= ~(mask1) # 清零第一个字节的低位
        packed_data[byte_index] |= (new_tile_value >> bits_in_second_byte) & mask1
        # 检查是否有第二个字节
        if byte_index + 1 < len(packed_data):
            packed_data[byte_index + 1] &= ~(mask2 << (8 - bits_in_second_byte)) # 清零第二个字节的高位
            packed_data[byte_index + 1] |= (new_tile_value << (8 - bits_in_second_byte)) & 0xFF
        else:
             logger.debug(f"update_tile_packed: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在，地图ID {map_id}。")

    # 将修改后的 bytearray 转换回 bytes 并返回
    return bytes(packed_data)