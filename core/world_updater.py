# core/world_updater.py
import logging
from typing import List, Tuple, Dict, Any
from core import database, config

logger = logging.getLogger(__name__)

# 定义地形常量等
PLAIN = 0
FOREST = 1
FARM_UNTILLED = 3

class WorldUpdater:
    """
    负责从数据库加载世界状态快照，在内存中执行游戏逻辑，
    并将计算出的变更集提交回数据库。
    """
    def __init__(self, config_obj: config.Config):
        """
        初始化 WorldUpdater。
        Args:
            config_obj: 包含游戏规则和参数的配置对象。
        """
        self.config = config_obj
        
    def update(self, map_id: int, current_tick: int) -> bool:
        """
        主更新入口点，由 Ticker 调用。
        负责调用游戏逻辑并处理异常。
        """
        try:
            return self._update_game_logic(map_id, current_tick)
        except Exception as e:
            logger.error(f"Critical error during update for map {map_id} at tick {current_tick}: {e}", exc_info=True)
            return False

    def _update_game_logic(self, map_id: int, current_tick: int) -> bool:
        """
        核心游戏逻辑实现，采用“读全量，写增量”模型。
        """
        # 1. 原子性地获取世界完整状态
        snapshot = database.get_world_snapshot(map_id)
        if not snapshot:
            logger.error(f"Cannot update: Failed to get world snapshot for map {map_id}.")
            return False
        
        # 2. 准备一个空的变更集来收集本轮的所有变化
        changeset = {
            "tile_changes": [],
            "villager_updates": [],
            "house_updates": [],
            "new_villagers": [],
            "new_houses": [],
            "deleted_villager_ids": [],
            "deleted_house_ids": []
        }
        
        # 3. 在内存中执行所有模拟和AI决策
        logger.debug(f"Simulating tick {current_tick} for map {map_id}...")
        
        # --- 示例逻辑：所有饥饿的村民都会变老 ---
        for villager in snapshot.villagers:
            villager['age_in_ticks'] += 1
            if villager['hunger'] > 0:
                villager['hunger'] -= 1
            # 将这个村民的变更加入列表
            changeset["villager_updates"].append(villager)
            
        # --- 示例逻辑：一个村民在(10,10)开垦农田 ---
        if snapshot.villagers:
            x, y = 10, 10
            # AI可以访问内存中的完整grid_2d来决策
            if snapshot.grid_2d[y][x] == PLAIN:
                new_tile_type = FARM_UNTILLED
                # 在内存中更新，供本轮后续逻辑使用
                snapshot.grid_2d[y][x] = new_tile_type
                # 记录变更
                changeset["tile_changes"].append((x, y, new_tile_type))
                # 记录事件
                database.log_event(map_id, current_tick, 'TERRAIN_CHANGE', 
                                   {'x': x, 'y': y, 'new_type': new_tile_type})

        # 4. 原子性地提交所有变更
        logger.debug(f"Committing changes for tick {current_tick}...")
        try:
            database.commit_changes(map_id, changeset)
        except Exception as e:
            logger.error(f"Failed to commit changeset for map {map_id}: {e}")
            return False # 提交失败，则此Tick失败

        return True