# core/villager_ai.py
import logging
from typing import Dict, Any, Optional, Tuple
from core.database import WorldSnapshot

# 引入地形常量
from .world_updater import PLAIN, WATER

logger = logging.getLogger(__name__)

def decide_next_action(villager: Dict[str, Any], snapshot: WorldSnapshot, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    根据村民的需求层次决定下一个行动。
    返回一个包含行动描述的字典，或者 None。
    """
    # 需求1：生存（未来扩展：如果饥饿，去找吃的）
    # if villager['hunger'] < 30:
    #     return {'type': 'EAT'}

    # 需求2：发展（种地）
    # 寻找一个可以开垦为农田的地方
    farmland_spot = find_best_farmland_spot(villager, snapshot)
    if farmland_spot:
        return {
            'type': 'TASK',
            'name': 'build_farmland',
            'target': farmland_spot
        }

    # 需求3：砍树（未来扩展）
    # 需求4：建房（未来扩展）

    # 如果无事可做
    return None

def find_best_farmland_spot(villager: Dict[str, Any], snapshot: WorldSnapshot) -> Optional[Tuple[int, int]]:
    """
    在村民周围寻找一个最佳的农田开垦点（平原且临水）。
    使用螺旋搜索算法，效率更高。
    """
    start_x, start_y = villager['x'], villager['y']
    grid = snapshot.grid_2d
    width, height = snapshot.width, snapshot.height
    
    # 定义邻居的相对坐标
    neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    # 简单的径向搜索，未来可以优化为螺旋搜索
    max_radius = 20 # 最多搜索20格远
    for r in range(1, max_radius):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r: continue # 只搜索圆环

                x, y = start_x + dx, start_y + dy

                # 检查边界和瓦片类型
                if not (0 <= x < width and 0 <= y < height): continue
                if grid[y][x] != PLAIN: continue

                # 检查是否临水
                is_adjacent_to_water = False
                for nx_offset, ny_offset in neighbors:
                    nx, ny = x + nx_offset, y + ny_offset
                    if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == WATER:
                        is_adjacent_to_water = True
                        break
                
                if is_adjacent_to_water:
                    logger.debug(f"Villager {villager['id']} found a valid farmland spot at ({x}, {y})")
                    return (x, y) # 找到第一个可用的就返回
    
    logger.debug(f"Villager {villager['id']} could not find a valid farmland spot.")
    return None