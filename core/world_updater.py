# core/world_updater.py
import logging
from typing import Tuple, Optional, List
from core import database

# --- 定义地形常量 ---
PLAIN = 0
FOREST = 1
WATER = 2
FARM_UNTILLED = 3  # 未耕种/未成熟耕地
FARM_TILLED = 4  # 已耕种/已成熟耕地

# --- 导入调试逻辑 ---
try:
    from .debug_updater import update_debug_logic

    DEBUG_UPDATER_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).warning(f"Debug updater not available: {e}")
    DEBUG_UPDATER_AVAILABLE = False
    update_debug_logic = None  # 确保变量存在

# --- 导入 3-bit 打包/解包函数 ---
# 假设这些函数已经添加到 database.py 中
# 如果它们在 database.py 的其他地方或在 world_updater.py 本身，请相应调整导入
# from .database import get_tile_packed, update_tile_packed # 如果在 database.py
# 或者，如果 pack/unpack 函数在 world_updater.py 本身，可以直接调用

# 为了兼容性和清晰性，我们在这里重新定义或导入它们
# *** 注意：最好将 pack_grid_to_3bit 和 unpack_3bit_bytes 移动到 core/database.py ***
# *** 或者创建一个 core/pack_utils.py 模块 ***
# 这里为了演示，我们假设它们在 database.py 或者我们在这里重新定义它们。
# 从之前的对话中复制过来：
def pack_grid_to_3bit(grid_2d: List[List[int]]) -> bytes:
    """将二维的瓦片地图数据打包成 3-bit/瓦片的 bytes 对象。"""
    if not grid_2d or not grid_2d[0]:
        return bytes()
    height = len(grid_2d)
    width = len(grid_2d[0])
    total_tiles = width * height
    packed_size = (total_tiles * 3 + 7) // 8
    packed_data = bytearray(packed_size)
    for i in range(total_tiles):
        y = i // width
        x = i % width
        value = grid_2d[y][x]
        if not (0 <= value <= 7):
            logging.getLogger(__name__).warning(f"Tile value {value} at ({x},{y}) is out of 3-bit range (0-7). Clamping.")
            value = max(0, min(7, value))
        bit_index = i * 3
        byte_index = bit_index // 8
        bit_offset = bit_index % 8
        if bit_offset <= 5:
            packed_data[byte_index] |= (value << (8 - 3 - bit_offset)) & 0xFF
        else:
            bits_in_first_byte = 8 - bit_offset
            bits_in_second_byte = 3 - bits_in_first_byte
            packed_data[byte_index] |= (value >> bits_in_second_byte) & ((1 << bits_in_first_byte) - 1)
            if byte_index + 1 < len(packed_data):
                packed_data[byte_index + 1] |= (value << (8 - bits_in_second_byte)) & 0xFF
    return bytes(packed_data)

def unpack_3bit_bytes(packed_bytes: bytes, width: int, height: int) -> List[List[int]]:
    """将 3-bit/瓦片打包的 bytes 对象解包成二维的瓦片地图列表。"""
    total_tiles = width * height
    expected_packed_size = (total_tiles * 3 + 7) // 8
    if len(packed_bytes) != expected_packed_size:
        logging.getLogger(__name__).warning(f"Unpack: Expected {expected_packed_size} bytes for {width}x{height} map, got {len(packed_bytes)}.")
    packed_data = bytearray(packed_bytes)
    grid_2d = [[0 for _ in range(width)] for _ in range(height)]
    for i in range(total_tiles):
        y = i // width
        x = i % width
        bit_index = i * 3
        byte_index = bit_index // 8
        bit_offset = bit_index % 8
        value = 0
        if bit_offset <= 5:
            mask = (1 << 3) - 1
            value = (packed_data[byte_index] >> (8 - 3 - bit_offset)) & mask
        else:
            bits_in_first_byte = 8 - bit_offset
            bits_in_second_byte = 3 - bits_in_first_byte
            part1 = (packed_data[byte_index] & ((1 << bits_in_first_byte) - 1)) << bits_in_second_byte
            part2 = (packed_data[byte_index + 1] >> (8 - bits_in_second_byte)) & ((1 << bits_in_second_byte) - 1) if (byte_index + 1 < len(packed_data)) else 0
            value = part1 | part2
        grid_2d[y][x] = value
    return grid_2d
# --- 3-bit 函数定义结束 ---

logger = logging.getLogger(__name__)

class WorldUpdater:
    """
    负责执行世界状态更新逻辑。
    """

    def __init__(self, use_debug_logic: bool = False):
        """
        初始化 WorldUpdater。
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
                f"WorldUpdater: Unexpected data format from database.get_map_by_id for ID {map_id}. Expected (width, height, map_data). Error: {e}"
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

    def save_map_data(
        self, map_id: int, grid_2d: Optional[List[List[int]]], width: int, height: int
    ) -> bool:
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
                logger.warning(
                    f"WorldUpdater: Failed to update map data for ID {map_id} in DB."
                )
            return success
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to pack/save map data for ID {map_id}: {e}")
            return False

    def update(self, map_id: int, current_tick: int) -> bool:
        """
        根据配置选择更新函数。
        这是 Ticker 调用的主要入口点。
        Args:
            map_id: 地图ID
            current_tick: 当前的 tick 数
        Returns:
            bool: 是否成功执行了更新 (或成功加载/保存，即使无变化)
        """
        if self.use_debug_logic and DEBUG_UPDATER_AVAILABLE:
            logger.debug(f"WorldUpdater: Using debug update logic for map {map_id}")
            return self._update_with_debug_logic_optimized(map_id, current_tick)
            # return self._update_with_debug_logic(map_id, current_tick) # 保留旧版本供对比
        else:
            # 默认行为：加载并保存数据（无变化）
            logger.debug(
                f"WorldUpdater: No update logic defined or debug logic disabled for map {map_id}. Loading and saving without changes."
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
            logger.error(f"WorldUpdater (Optimized): Invalid data format for map {map_id}: {e}")
            return False
        if not original_packed_bytes:
             logger.error(f"WorldUpdater (Optimized): Map ID {map_id} has no data.")
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
                f"WorldUpdater (Optimized): Debug logic ran but no logical changes for map {map_id} at tick {current_tick}."
            )
            return True # 认为更新成功，即使没有数据库写入

        # 5. 如果有逻辑改变，找出差异并更新打包数据
        logger.info(
            f"WorldUpdater (Optimized): Changes detected by debug logic for map {map_id}, applying diffs..."
        )
        
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
                    old_value = database.get_tile_packed(map_id, x, y, width, height, original_packed_bytes)
                except (ValueError, IndexError) as e:
                    logger.error(f"WorldUpdater (Optimized): Error reading old tile value at ({x},{y}) for map {map_id}: {e}")
                    # 如果读取旧值失败，为了安全起见，我们仍然尝试更新
                    old_value = -1 # 设置一个不可能的值，确保下面的 if 条件成立

                # 7. 如果值发生了变化，则更新 current_packed_bytes
                if new_value != old_value:
                    try:
                        # 使用 database.py 的 update_tile_packed 更新 current_packed_bytes
                        # 注意：database.update_tile_packed 返回更新后的 bytes，我们需要保留这个引用
                        # 为了避免反复创建 bytes 对象，我们可以直接操作 bytearray
                        # 但 database.update_tile_packed 设计为返回新的 bytes
                        # 我们需要调整 database.update_tile_packed 的实现，或者在这里直接调用其内部逻辑
                        # 为简化，我们假设 database.update_tile_packed 可以接受 bytearray 并就地修改
                        # 或者我们接收它返回的新 bytes 并赋值回去
                        # *** 关键点：database.update_tile_packed 需要被修改以支持 bytearray ***
                        # *** 或者，我们在这里复制其逻辑 ***
                        
                        # --- 方案 A: 假设 database.update_tile_packed 可以处理 bytearray 并返回 ---
                        # current_packed_bytes = database.update_tile_packed(map_id, x, y, new_value, width, height, current_packed_bytes)
                        # actual_db_change = True
                        
                        # --- 方案 B: 在此文件中复制 update_tile_packed 逻辑 (推荐，避免修改 database.py API) ---
                        # 我们调用本地的辅助函数来更新 bytearray
                        current_packed_bytes = self._apply_tile_update_to_bytearray(
                            current_packed_bytes, x, y, new_value, width, height, map_id
                        )
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
            return True # 逻辑上已更新，无需数据库写入


    def _apply_tile_update_to_bytearray(self, packed_data: bytearray, x: int, y: int, new_tile_value: int, width: int, height: int, map_id: int) -> bytearray:
        """
        将单个瓦片的更新应用到 bytearray 形式的 3-bit 打包数据上。
        这是 database.update_tile_packed 逻辑的本地副本，用于直接操作 bytearray。
        """
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"坐标 ({x}, {y}) 超出地图范围（宽:{width}, 高:{height}）。")
        if not (0 <= new_tile_value <= 7):
             logger.warning(f"_apply_tile_update_to_bytearray: 瓦片值 {new_tile_value} 超出 3-bit 范围 (0-7)，地图ID {map_id}。已截断。")
             new_tile_value = max(0, min(7, new_tile_value))

        # total_tiles = width * height # 不需要计算总大小，因为我们直接操作传入的 bytearray
        # expected_packed_size = (total_tiles * 3 + 7) // 8 # 不需要检查大小，假设传入的 bytearray 是正确的
        # if len(packed_data) != expected_packed_size: # 可选检查
        #      logger.warning(f"_apply_tile_update_to_bytearray: 数据大小 ({len(packed_data)}) 与预期 ({expected_packed_size}) 不符，地图ID {map_id}。")

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
                 logger.debug(f"_apply_tile_update_to_bytearray: 瓦片 ({x},{y}) 的值跨越字节边界，但下一个字节不存在，地图ID {map_id}。")
        
        # bytearray 是可变对象，直接修改即可，无需返回
        # 但为了与 database.update_tile_packed 的签名兼容，我们返回它
        return packed_data

    # --- 保留旧的方法供对比 ---
    def _update_with_debug_logic(self, map_id: int, current_tick: int) -> bool:
        """
        使用调试逻辑更新地图 (旧版本，全量加载/修改/打包/保存)。
        """
        grid_2d, width, height = self.load_map_data(map_id)
        if grid_2d is None:
            return False
        if DEBUG_UPDATER_AVAILABLE and update_debug_logic is not None:
            changed = update_debug_logic(grid_2d, width, height, current_tick)
        else:
            logger.error("Debug update logic is not available.")
            return False
        if changed:
            logger.info(
                f"WorldUpdater (Old): Changes detected by debug logic for map {map_id}, saving..."
            )
            return self.save_map_data(map_id, grid_2d, width, height)
        else:
            logger.debug(
                f"WorldUpdater (Old): Debug logic ran but no changes for map {map_id} at tick {current_tick}."
            )
            return True

world_updater_instance = WorldUpdater(use_debug_logic=False)