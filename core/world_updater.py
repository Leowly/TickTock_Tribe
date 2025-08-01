# core/world_updater.py
import logging
from typing import Dict, List, Any
from core import database, config
from core.villager_manager import VillagerManager
logger = logging.getLogger(__name__)

class WorldUpdater:
    def __init__(self, config_obj: config.Config):
        self.config = config_obj
        self.villager_manager = VillagerManager(config_obj)
        
    def update(self, map_id: int, current_tick: int) -> bool:
        try:
            return self._update_game_logic(map_id, current_tick)
        except Exception as e:
            logger.error(f"Critical error during update for map {map_id} at tick {current_tick}: {e}", exc_info=True)
            return False

    def _update_game_logic(self, map_id: int, current_tick: int) -> bool:
        """
        【新】此函数现在能正确处理 villager_manager 返回的各种变更请求。
        """
        snapshot = database.get_world_snapshot(map_id)
        if not snapshot:
            logger.error(f"Cannot update: Failed to get world snapshot for map {map_id}.")
            return False
        
        # 加载最新状态
        self.villager_manager.load_from_database(snapshot)
        
        # 执行模拟并获取所有变更
        villager_changes = self.villager_manager.update_villagers(current_tick, snapshot.grid_2d)
        
        # 如果有任何变更，则提交到数据库
        if any(villager_changes.values()):
            try:
                database.commit_changes(map_id, villager_changes)
            except Exception as e:
                logger.error(f"Failed to commit changeset for map {map_id}: {e}")
                return False

        return True