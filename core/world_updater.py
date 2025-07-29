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
        初始化 WorldUpdater，并预加载配置参数以提高性能。
        """
        self.config = config_obj
        
        # 预加载配置参数，避免在循环中重复调用 get 方法
        villager_cfg = self.config.get_villager()
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 1)
        self.ticks_to_starve = villager_cfg.get('ticks_to_starve', 100)
        
    def update(self, map_id: int, current_tick: int) -> bool:
        """
        主更新入口点，由 Ticker 调用。
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
        
        # --- 核心逻辑更新：应用新的时间和消耗规则 ---
        villagers_to_process = list(snapshot.villagers) # 创建副本以安全地处理死亡
        
        for villager in villagers_to_process:
            # a. 年龄增长
            villager['age_in_ticks'] += 1
            
            # b. 饥饿度下降 (使用配置中的值)
            if villager['hunger'] > 0:
                villager['hunger'] -= self.hunger_loss_per_tick
            
            # c. 死亡判定
            if villager['hunger'] <= 0:
                logger.info(f"Villager {villager['id']} has died of starvation.")
                # 记录要删除的村民ID
                changeset["deleted_villager_ids"].append(villager['id'])
                # (未来可能还需要处理房屋空位等逻辑)
                # 从当前tick的处理中跳过此村民
                continue

            # 如果村民还活着，则将他的状态变更加入更新列表
            changeset["villager_updates"].append(villager)
            
        # --- 示例逻辑：一个村民在(10,10)开垦农田 (保持不变) ---
        if snapshot.villagers:
            x, y = 10, 10
            if snapshot.grid_2d[y][x] == PLAIN:
                new_tile_type = FARM_UNTILLED
                snapshot.grid_2d[y][x] = new_tile_type
                changeset["tile_changes"].append((x, y, new_tile_type))
                database.log_event(map_id, current_tick, 'TERRAIN_CHANGE', 
                                   {'x': x, 'y': y, 'new_type': new_tile_type})

        # 4. 原子性地提交所有变更
        logger.debug(f"Committing changes for tick {current_tick}...")
        try:
            # 注意：commit_changes 需要被扩展以处理删除操作
            database.commit_changes(map_id, changeset)
        except Exception as e:
            logger.error(f"Failed to commit changeset for map {map_id}: {e}")
            return False

        return True