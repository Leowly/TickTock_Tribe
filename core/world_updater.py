# core/world_updater.py
import time
import logging
from typing import Tuple, Optional, List
from core import database

# --- 定义地形常量 ---
PLAIN = 0
FOREST = 1
WATER = 2
FARM_UNTILLED = 3  # 未耕种/未成熟耕地
FARM_TILLED = 4    # 已耕种/已成熟耕地

logger = logging.getLogger(__name__)

class WorldUpdater:
    """
    负责执行世界状态更新逻辑。
    """

    def __init__(self):
        pass

    def load_map_data(self, map_id: int) -> Tuple[Optional[List[List[int]]], int, int]:
        """
        从数据库加载地图数据。
        Returns:
            (grid_2d: List[List[int]], width: int, height: int) or (None, 0, 0) if failed.
        """
        # 调用 database.get_map_by_id，它返回 (width, height, map_data)
        # 根据你提供的最新 database.py 文件
        map_data_row = database.get_map_by_id(map_id)
        if not map_data_row:
            logger.error(f"WorldUpdater: Map ID {map_id} not found in database.")
            return None, 0, 0

        # --- 正确解包来自 database.get_map_by_id 的元组 ---
        # database.py 中定义 get_map_by_id 返回 (width, height, map_data)
        try:
            width, height, map_bytes = map_data_row
        except ValueError as e:
            logger.error(f"WorldUpdater: Unexpected data format from database.get_map_by_id for ID {map_id}. Expected (width, height, map_data). Error: {e}")
            logger.debug(f"WorldUpdater: Received data row: {map_data_row}")
            return None, 0, 0
        # --- 解包结束 ---

        if not map_bytes:
            logger.error(f"WorldUpdater: Map ID {map_id} has no data.")
            return None, 0, 0

        try:
            # 将 bytes 转换为 1D list
            flat_tiles = list(map_bytes)
            # 转换为 2D list
            grid_2d = [flat_tiles[i * width:(i + 1) * width] for i in range(height)]
            return grid_2d, width, height
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to parse map data for ID {map_id}: {e}")
            return None, 0, 0

    def save_map_data(self, map_id: int, grid_2d: List[List[int]], width: int, height: int) -> bool:
        """
        将更新后的地图数据保存回数据库。
        """
        try:
            # 将 2D list 转换回 flat list
            flat_tiles = [tile for row in grid_2d for tile in row]
            # 转换为 bytes
            map_bytes = bytes(flat_tiles)
            # 保存到数据库 (调用 database.py 的函数)
            success = database.update_map_data(map_id, map_bytes) # 确保 database.py 有此函数
            if success:
                logger.debug(f"WorldUpdater: Saved updated map data for ID {map_id}.")
            else:
                logger.warning(f"WorldUpdater: Failed to update map data for ID {map_id} in DB.")
            return success
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to save map data for ID {map_id}: {e}")
            return False

    def update_debug(self, map_id: int, current_tick: int) -> bool:
        """
        调试用更新函数：
        1. 将一个平原 (PLAIN) 按顺序变为未耕种耕地 (FARM_UNTILLED)。
        2. 将所有未耕种耕地 (FARM_UNTILLED) 变为已耕种耕地 (FARM_TILLED)。
        Args:
            map_id: 地图ID
            current_tick: 当前的 tick 数
        Returns:
            bool: 是否成功执行了更新
        """
        logger.info(f"WorldUpdater: Running debug update for map {map_id} at tick {current_tick}")
        
        grid_2d, width, height = self.load_map_data(map_id)
        if grid_2d is None:
            return False

        # --- 调试逻辑 1: 将一个 PLAIN 变为 FARM_UNTILLED ---
        total_tiles = width * height
        if total_tiles > 0:
            # 使用 current_tick 来确定要改变的格子
            target_index_1d = current_tick % total_tiles
            target_y = target_index_1d // width
            target_x = target_index_1d % width

            if 0 <= target_y < height and 0 <= target_x < width:
                # 检查该格子是否为平原
                if grid_2d[target_y][target_x] == PLAIN:
                    grid_2d[target_y][target_x] = FARM_UNTILLED # <-- 使用新常量
                    logger.debug(f"WorldUpdater: Changed tile ({target_x}, {target_y}) to FARM_UNTILLED.")

        # --- 调试逻辑 2: 将所有 FARM_UNTILLED 变为 FARM_TILLED ---
        # 这模拟了作物立即成熟的过程
        changed_any = False # 标记是否有任何更改
        for y in range(height):
            for x in range(width):
                if grid_2d[y][x] == FARM_UNTILLED:
                    grid_2d[y][x] = FARM_TILLED # <-- 使用新常量
                    logger.debug(f"WorldUpdater: Matured farm tile ({x}, {y}).")
                    changed_any = True

        # --- 保存 ---
        # 为了调试清晰，我们总是保存
        return self.save_map_data(map_id, grid_2d, width, height)

# 创建一个全局实例供 ticker 使用
world_updater_instance = WorldUpdater()