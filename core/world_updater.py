# core/world_updater.py
import logging
from typing import Tuple, Optional, List
from core import database

logger = logging.getLogger(__name__)

# - 定义地形常量 -
PLAIN = 0
FOREST = 1
WATER = 2
FARM_UNTILLED = 3  # 未耕种/未成熟耕地
FARM_TILLED = 4    # 已耕种/已成熟耕地
HOUSE = 5          # 新增：房子地形标识 (示例，实际可能用实体表存储)

# - 导入调试逻辑 -
try:
    from .debug_updater import update_debug_logic
    DEBUG_UPDATER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Debug updater not available: {e}")
    DEBUG_UPDATER_AVAILABLE = False
    update_debug_logic = None  # 确保变量存在

# --- 3-bit 数据打包/解包函数 (移到这里，因为它们是世界更新器处理数据的核心部分) ---
def pack_grid_to_3bit(grid_2d: List[List[int]]) -> bytes:
    """将二维的瓦片地图数据打包成 3-bit/瓦片的 bytes 对象。"""
    if not grid_2d or not grid_2d[0]:
        return bytes()
    height = len(grid_2d)
    width = len(grid_2d[0])
    total_tiles = width * height
    packed_size = (total_tiles * 3 + 7) // 8

    # 初始化一个足够大的 bytearray
    packed_data = bytearray(packed_size)

    for y in range(height):
        for x in range(width):
            tile_value = grid_2d[y][x]
            if not (0 <= tile_value <= 7):
                logger.warning(f"pack_grid_to_3bit: 瓦片值 {tile_value} 超出 3-bit 范围 (0-7)。已截断。")
                tile_value = max(0, min(7, tile_value))

            i = y * width + x
            bit_index = i * 3
            byte_index = bit_index // 8
            bit_offset = bit_index % 8

            if bit_offset <= 5:
                shift = 8 - 3 - bit_offset
                packed_data[byte_index] |= (tile_value << shift) & 0xFF
            else:
                bits_in_first_byte = 8 - bit_offset
                bits_in_second_byte = 3 - bits_in_first_byte
                packed_data[byte_index] |= (tile_value >> bits_in_second_byte) & ((1 << bits_in_first_byte) - 1)
                if byte_index + 1 < len(packed_data):
                    packed_data[byte_index + 1] |= (tile_value << (8 - bits_in_second_byte)) & 0xFF

    return bytes(packed_data)

def unpack_3bit_bytes(packed_bytes: bytes, width: int, height: int) -> List[List[int]]:
    """将 3-bit/瓦片的 bytes 对象解包成二维的瓦片地图数据列表。"""
    if not packed_bytes:
        return [[0 for _ in range(width)] for _ in range(height)]

    total_tiles = width * height
    expected_packed_size = (total_tiles * 3 + 7) // 8
    if len(packed_bytes) != expected_packed_size:
        logger.warning(f"unpack_3bit_bytes: 数据大小 ({len(packed_bytes)}) 与预期 ({expected_packed_size}) 不符。")

    # 初始化二维列表
    grid_2d = [[0 for _ in range(width)] for _ in range(height)]

    for y in range(height):
        for x in range(width):
            i = y * width + x
            bit_index = i * 3
            byte_index = bit_index // 8
            bit_offset = bit_index % 8

            if byte_index >= len(packed_bytes):
                raise IndexError(f"解包时字节索引 {byte_index} 超出范围 {len(packed_bytes)}。")

            value = 0
            if bit_offset <= 5:
                mask = (1 << 3) - 1
                value = (packed_bytes[byte_index] >> (8 - 3 - bit_offset)) & mask
            else:
                bits_in_first_byte = 8 - bit_offset
                bits_in_second_byte = 3 - bits_in_first_byte
                part1 = (packed_bytes[byte_index] & ((1 << bits_in_first_byte) - 1)) << bits_in_second_byte
                if byte_index + 1 < len(packed_bytes):
                    part2 = (packed_bytes[byte_index + 1] >> (8 - bits_in_second_byte)) & ((1 << bits_in_second_byte) - 1)
                else:
                    part2 = 0
                    logger.debug(f"unpack_3bit_bytes: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在。")
                value = part1 | part2

            grid_2d[y][x] = value

    return grid_2d


class WorldUpdater:
    """
    负责加载地图、应用更新逻辑、打包/解包数据，并与数据库交互。
    """

    def __init__(self, use_debug_logic: bool = False):
        """
        Args:
            use_debug_logic (bool): 是否使用调试更新逻辑。默认为 False。
        """
        self.use_debug_logic = use_debug_logic

    def load_map_data(self, map_id: int) -> Tuple[Optional[List[List[int]]], int, int]:
        """
        从数据库加载地图数据 (现在是 3-bit 打包格式)。
        Returns:
            (grid_2d: List[List[int]], width: int, height: int) or (None, 0, 0) if failed.
        """
        map_data_row = database.get_map_by_id(map_id)
        if not map_data_row:
            logger.error(f"WorldUpdater: Map ID {map_id} not found in database.")
            return None, 0, 0
        try:
            width, height, map_bytes = map_data_row
        except ValueError as e:
            logger.error(
                f"WorldUpdater: Unexpected data format from database.get_map_by_id for ID {map_id}. "
                f"Expected (width, height, map_data). Error: {e}"
            )
            logger.debug(f"WorldUpdater: Received data row: {map_data_row}")
            return None, 0, 0
        if not map_bytes:
            logger.error(f"WorldUpdater: Map ID {map_id} has no data.")
            return None, 0, 0
        try:
            # 使用解包函数将打包数据转换为二维列表
            grid_2d = unpack_3bit_bytes(map_bytes, width, height)
            return grid_2d, width, height
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to parse/unpack map data for ID {map_id}: {e}")
            return None, 0, 0

    def save_map_data(self, map_id: int, grid_2d: Optional[List[List[int]]], width: int, height: int) -> bool:
        """
        将更新后的地图数据打包并保存回数据库。
        """
        if grid_2d is None:
            logger.error(f"WorldUpdater: grid_2d is None for map ID {map_id}")
            return False
        try:
            # 使用打包函数将二维列表转换为 3-bit bytes
            packed_map_bytes = pack_grid_to_3bit(grid_2d)
            # 保存打包后的数据到数据库
            success = database.update_map_data(map_id, packed_map_bytes)
            if success:
                logger.debug(f"WorldUpdater: Saved updated (packed) map data for ID {map_id}.")
            else:
                logger.warning(f"WorldUpdater: Failed to update map data for ID {map_id} in DB.")
            return success
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to pack/save map data for ID {map_id}: {e}")
            return False

    def update(self, map_id: int, current_tick: int) -> bool:
        """
        根据配置选择更新函数。这是 Ticker 调用的主要入口点。
        Args:
            map_id: 地图ID
            current_tick: 当前的 tick 数
        Returns:
            bool: 是否成功执行了更新 (或成功加载/保存，即使无变化)
        """
        if self.use_debug_logic and DEBUG_UPDATER_AVAILABLE:
            logger.debug(f"WorldUpdater: Using debug update logic for map {map_id}")
            return self._update_with_debug_logic_optimized(map_id, current_tick)
            # return self._update_with_debug_logic(map_id, current_tick) # 旧版本已移除
        else:
            # 默认行为：加载并保存数据（无变化）
            logger.debug(
                f"WorldUpdater: No update logic defined or debug logic disabled for map {map_id}. "
                f"Loading and saving without changes."
            )
            grid_data_result = self.load_map_data(map_id)
            if grid_data_result[0] is not None:
                grid_2d, width, height = grid_data_result
                return self.save_map_data(map_id, grid_2d, width, height)
            return False

    # --- 新增/修改的方法：优化的更新逻辑 ---
    def _update_with_debug_logic_optimized(self, map_id: int, current_tick: int) -> bool:
        """
        使用调试逻辑更新地图，并优化数据库写入。
        只有在瓦片值真正改变时，才更新打包的数据，最后一次性写回数据库。
        """
        # 1. 获取地图元数据和原始打包数据
        map_data_row = database.get_map_by_id(map_id)
        if not map_data_row:
            logger.error(f"WorldUpdater (Optimized): Map ID {map_id} not found in database.")
            return False
        try:
            width, height, original_packed_bytes = map_data_row
        except ValueError as e:
            logger.error(
                f"WorldUpdater (Optimized): Unexpected data format from database.get_map_by_id for ID {map_id}. "
                f"Expected (width, height, map_data). Error: {e}"
            )
            return False

        # 2. 解包数据以供 debug_updater 使用
        try:
            grid_2d = unpack_3bit_bytes(original_packed_bytes, width, height)
        except Exception as e:
            logger.error(f"WorldUpdater (Optimized): Failed to unpack map data for ID {map_id}: {e}")
            return False

        # 3. 运行调试逻辑
        if DEBUG_UPDATER_AVAILABLE and update_debug_logic is not None:
            # update_debug_logic 会直接修改传入的 grid_2d
            changed_in_grid = update_debug_logic(grid_2d, width, height, current_tick)
        else:
            logger.error("Debug update logic is not available.")
            return False

        # 4. 如果没有逻辑上的改变，直接返回成功
        if not changed_in_grid:
            logger.debug(
                f"WorldUpdater (Optimized): Debug logic ran but no logical changes for map {map_id} at tick {current_tick}.")
            return True  # 认为更新成功，即使没有数据库写入

        # 5. 如果有逻辑改变，找出差异并更新打包数据
        logger.info(f"WorldUpdater (Optimized): Changes detected by debug logic for map {map_id}, applying diffs...")
        # 创建一个可修改的打包数据副本
        current_packed_bytes = bytearray(original_packed_bytes)
        # 标记是否实际发生了字节级别的改变
        actual_db_change = False

        # 6. 遍历二维网格，找出被修改的瓦片
        for y in range(height):
            for x in range(width):
                # 从 grid_2d 获取新值
                new_value = grid_2d[y][x]
                # 从原始打包数据中获取旧值
                try:
                    # 内部辅助函数：从 bytearray 读取 3-bit 值
                    old_value = self._get_tile_from_bytearray(x, y, width, height, current_packed_bytes)
                except (ValueError, IndexError) as e:
                    logger.error(f"WorldUpdater (Optimized): Error reading old tile value at ({x},{y}) for map {map_id}: {e}")
                    # 如果读取旧值失败，为了安全起见，我们仍然尝试更新
                    old_value = -1  # 设置一个不可能的值，确保下面的 if 条件成立

                # 7. 如果值发生了变化，则更新 current_packed_bytes
                if new_value != old_value:
                    try:
                        # 内部辅助函数：更新 bytearray 中的 3-bit 值
                        current_packed_bytes = self._apply_tile_update_to_bytearray(current_packed_bytes, x, y, new_value, width, height, map_id)
                        actual_db_change = True
                    except (ValueError, IndexError) as e:
                        logger.error(f"WorldUpdater (Optimized): Error updating tile at ({x},{y}) for map {map_id}: {e}")
                        # 即使单个瓦片更新失败，也继续处理其他瓦片

        # 8. 如果实际数据有改变，则写回数据库
        if actual_db_change:
            logger.debug(f"WorldUpdater (Optimized): Writing updated packed data back to DB for map {map_id}.")
            success = database.update_map_data(map_id, bytes(current_packed_bytes))
            if success:
                logger.info(f"WorldUpdater (Optimized): Successfully saved diff-updated map data for ID {map_id}.")
            else:
                logger.error(f"WorldUpdater (Optimized): Failed to save diff-updated map data for ID {map_id}.")
            return success
        else:
            # 理论上 changed_in_grid 为 True 但 actual_db_change 为 False 的情况很少见
            # 但为了健壮性，我们处理这种情况
            logger.debug(f"WorldUpdater (Optimized): Logical changes detected but no actual byte diffs for map {map_id}.")
            return True  # 逻辑上已更新，无需数据库写入

    # --- 内部辅助函数：直接操作 bytearray (优化用) ---
    def _get_tile_from_bytearray(self, x: int, y: int, width: int, height: int, packed_data: bytearray) -> int:
        """从 bytearray 形式的 3-bit 打包数据中读取瓦片值。"""
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")

        i = y * width + x
        bit_index = i * 3
        byte_index = bit_index // 8
        bit_offset = bit_index % 8

        if byte_index >= len(packed_data):
            raise IndexError(f"计算出的字节索引 {byte_index} 超出数据范围 {len(packed_data)}。")

        value = 0
        if bit_offset <= 5:
            mask = (1 << 3) - 1
            value = (packed_data[byte_index] >> (8 - 3 - bit_offset)) & mask
        else:
            bits_in_first_byte = 8 - bit_offset
            bits_in_second_byte = 3 - bits_in_first_byte
            part1 = (packed_data[byte_index] & ((1 << bits_in_first_byte) - 1)) << bits_in_second_byte
            if byte_index + 1 < len(packed_data):
                part2 = (packed_data[byte_index + 1] >> (8 - bits_in_second_byte)) & ((1 << bits_in_second_byte) - 1)
            else:
                part2 = 0
                logger.debug(f"_get_tile_from_bytearray: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在。")
            value = part1 | part2
        return value

    def _apply_tile_update_to_bytearray(self, packed_data: bytearray, x: int, y: int, new_tile_value: int, width: int, height: int, map_id: int) -> bytearray:
        """
        将单个瓦片的更新应用到 bytearray 形式的 3-bit 打包数据上。
        """
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")
        if not (0 <= new_tile_value <= 7):
            logger.warning(f"_apply_tile_update_to_bytearray: 瓦片值 {new_tile_value} 超出 3-bit 范围 (0-7)，地图ID {map_id}。已截断。")
            new_tile_value = max(0, min(7, new_tile_value))

        i = y * width + x
        bit_index = i * 3
        byte_index = bit_index // 8
        bit_offset = bit_index % 8

        if byte_index >= len(packed_data):
            raise IndexError(f"计算出的字节索引 {byte_index} 超出数据范围 {len(packed_data)}。")

        # 清除旧的 3 位值
        if bit_offset <= 5:
            mask = (1 << 3) - 1
            shift = 8 - 3 - bit_offset
            packed_data[byte_index] &= ~(mask << shift)
            packed_data[byte_index] |= (new_tile_value << shift) & 0xFF
        else:
            bits_in_first_byte = 8 - bit_offset
            bits_in_second_byte = 3 - bits_in_first_byte
            mask1 = (1 << bits_in_first_byte) - 1
            mask2 = (1 << bits_in_second_byte) - 1
            packed_data[byte_index] &= ~(mask1)
            packed_data[byte_index] |= (new_tile_value >> bits_in_second_byte) & mask1
            if byte_index + 1 < len(packed_data):
                packed_data[byte_index + 1] &= ~(mask2 << (8 - bits_in_second_byte))
                packed_data[byte_index + 1] |= (new_tile_value << (8 - bits_in_second_byte)) & 0xFF
            else:
                logger.debug(f"_apply_tile_update_to_bytearray: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在，地图ID {map_id}。")

        return packed_data # bytearray 是可变对象，但为了接口一致性，我们返回它

# 创建全局实例
world_updater_instance = WorldUpdater(use_debug_logic=False)
