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
        从数据库加载地图数据。
        Returns:
            (grid_2d: List[List[int]], width: int, height: int) or (None, 0, 0) if failed.
        """
        # 调用 database.get_map_by_id，它返回 (width, height, map_data)
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
            # 将 bytes 转换为 1D list
            flat_tiles = list(map_bytes)
            # 转换为 2D list
            grid_2d = [flat_tiles[i * width : (i + 1) * width] for i in range(height)]
            return grid_2d, width, height
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to parse map data for ID {map_id}: {e}")
            return None, 0, 0

    def save_map_data(
        self, map_id: int, grid_2d: Optional[List[List[int]]], width: int, height: int
    ) -> bool:
        """
        将更新后的地图数据保存回数据库。
        """
        if grid_2d is None:
            logger.error(f"WorldUpdater: grid_2d is None for map ID {map_id}")
            return False
        try:
            # 将 2D list 转换回 flat list
            flat_tiles = [tile for row in grid_2d for tile in row]
            # 转换为 bytes
            map_bytes = bytes(flat_tiles)
            # 保存到数据库
            success = database.update_map_data(map_id, map_bytes)
            if success:
                logger.debug(f"WorldUpdater: Saved updated map data for ID {map_id}.")
            else:
                logger.warning(
                    f"WorldUpdater: Failed to update map data for ID {map_id} in DB."
                )
            return success
        except Exception as e:
            logger.error(f"WorldUpdater: Failed to save map data for ID {map_id}: {e}")
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
            return self._update_with_debug_logic(map_id, current_tick)
        else:
            # 默认行为：如果未启用调试逻辑或调试逻辑不可用，则加载并保存数据（无变化）
            # 这确保了 ticker 认为更新是“成功”的，即使没有实际改变。
            logger.debug(
                f"WorldUpdater: No update logic defined or debug logic disabled for map {map_id}. Loading and saving without changes."
            )
            grid_data_result = self.load_map_data(map_id)
            if grid_data_result[0] is not None:  # 如果加载成功
                grid_2d, width, height = grid_data_result
                # 即使没有变化也保存，保持与 ticker 的兼容性
                return self.save_map_data(map_id, grid_2d, width, height)
            return False  # 加载失败则返回 False

    def _update_with_debug_logic(self, map_id: int, current_tick: int) -> bool:
        """
        使用调试逻辑更新地图。
        """
        grid_2d, width, height = self.load_map_data(map_id)
        # 如果加载失败，grid_2d 会是 None，此时应立即返回 False 表示更新失败
        if grid_2d is None:
            return False
        if DEBUG_UPDATER_AVAILABLE and update_debug_logic is not None:
            changed = update_debug_logic(grid_2d, width, height, current_tick)
        else:
            logger.error("Debug update logic is not available.")
            return False
        if changed:
            logger.info(
                f"WorldUpdater: Changes detected by debug logic for map {map_id}, saving..."
            )
            return self.save_map_data(map_id, grid_2d, width, height)
        else:
            # 如果没有变化（例如，没有 PLAIN 格子了），也认为更新成功
            logger.debug(
                f"WorldUpdater: Debug logic ran but no changes for map {map_id} at tick {current_tick}."
            )
            return True

world_updater_instance = WorldUpdater(use_debug_logic=False)
