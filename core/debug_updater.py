# core/debug_updater.py
import random
import logging
from typing import List, Tuple

# 定义地形常量，避免导入依赖
PLAIN = 0
FARM_MATURE = 4  # 修正：使用FARM_MATURE而不是FARM_TILLED

logger = logging.getLogger(__name__)


def update_debug_logic(
    grid_2d: List[List[int]], width: int, height: int, current_tick: int
) -> bool:
    """
    调试用更新逻辑（渐进式转换 PLAIN 为 FARM_MATURE）：
    1. 找到所有现存的 PLAIN (0) 格子。
    2. 每个 tick，将其中一定比例（例如 1%）随机转换为 FARM_MATURE (4)。
    Args:
        grid_2d: 二维地图数据列表 (会在此列表上直接修改)。
        width: 地图宽度。
        height: 地图高度。
        current_tick: 当前的 tick 数 (虽然本次逻辑未直接使用，但保留参数)。
    Returns:
        bool: 是否成功执行了更新 (只要有更改就返回 True)。
    """
    # --- 注意：这个函数直接修改传入的 grid_2d 列表 ---

    logger.info(f"DebugUpdater: Running debug logic at tick {current_tick}")

    changed_any = False
    plain_coordinates: List[Tuple[int, int]] = []  # 用于存储所有 PLAIN 格子的 (y, x) 坐标

    # --- 步骤 1: 遍历地图，收集所有 PLAIN 格子的坐标 ---
    for y in range(height):
        for x in range(width):
            if grid_2d[y][x] == PLAIN:
                plain_coordinates.append((y, x))

    # --- 步骤 2: 如果没有 PLAIN 格子，直接返回 False (表示无变化) ---
    if not plain_coordinates:
        logger.info("DebugUpdater: No PLAIN tiles available for conversion.")
        return False  # 没有变化

    # --- 步骤 3: 计算本次要转换的格子数量 ---
    # 例如，每次转换当前 PLAIN 格子数量的 1%
    conversion_rate = 0.01
    num_to_convert = max(
        1, int(len(plain_coordinates) * conversion_rate)
    )  # 确保至少转换1个

    # --- 步骤 4: 随机选择要转换的 PLAIN 格子 ---
    # random.sample 会随机选择指定数量的不重复元素
    coordinates_to_convert = random.sample(plain_coordinates, num_to_convert)

    # --- 步骤 5: 执行转换 ---
    for y, x in coordinates_to_convert:
        grid_2d[y][x] = FARM_MATURE
        logger.debug(f"DebugUpdater: Converted PLAIN tile ({x}, {y}) to FARM_MATURE.")
        changed_any = True

    # --- 步骤 6: 返回是否发生了更改 ---
    if changed_any:
        logger.info(
            f"DebugUpdater: Converted {num_to_convert} PLAIN tiles to FARM_MATURE."
        )
    return changed_any

