# core/world_updater.py
import logging
from typing import Dict, List, Any
from core import database, config
from core.villager_manager import VillagerManager
logger = logging.getLogger(__name__)

# 定义地形常量等
PLAIN = 0
FOREST = 1
WATER = 2
FARM_UNTILLED = 3
FARM_MATURE = 4

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
        
        # 初始化村民管理器
        self.villager_manager = VillagerManager(config_obj)
        
        # 预加载农田成熟配置
        farming_cfg = self.config.get_farming()
        self.farm_mature_ticks = farming_cfg.get('farm_mature_ticks', 30)
        
        # 农田成熟时间跟踪
        self.farm_maturity_tracker = {}  # {(x, y): creation_tick}
        
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
        核心游戏逻辑实现，采用"读全量，写增量"模型。
        """
        # 1. 原子性地获取世界完整状态
        snapshot = database.get_world_snapshot(map_id)
        if not snapshot:
            logger.error(f"Cannot update: Failed to get world snapshot for map {map_id}.")
            return False
        
        # 2. 准备一个空的变更集
        changeset: Dict[str, List[Any]] = {
            "tile_changes": [], 
            "villager_updates": [], 
            "house_updates": [],
            "new_villagers": [], 
            "new_houses": [], 
            "deleted_villager_ids": [],
            "deleted_house_ids": []
        }
        
        # 3. 核心AI与模拟循环
        logger.debug(f"Simulating tick {current_tick} for map {map_id}...")
        
        # 从数据库加载村民和房屋数据到VillagerManager
        self.villager_manager.load_from_database(snapshot)
        
        # 如果是第一个tick，创建初始村民
        if current_tick == 0:
            world_center_x = len(snapshot.grid_2d[0]) // 2
            world_center_y = len(snapshot.grid_2d) // 2
            initial_villagers = self.villager_manager.create_initial_villagers(world_center_x, world_center_y)
            changeset["new_villagers"].extend(initial_villagers)
        
        # 更新村民状态
        villager_changes = self.villager_manager.update_villagers(current_tick, snapshot.grid_2d)
        
        # 合并村民变更
        for key in villager_changes:
            if key in changeset:
                changeset[key].extend(villager_changes[key])
        
        # 4. 原子性地提交所有变更
        # 检查是否有任何变更发生，避免不必要的数据库写入
        if any(changeset.values()):
            logger.debug(f"Committing changes for tick {current_tick}...")
            try:
                database.commit_changes(map_id, changeset)
            except Exception as e:
                logger.error(f"Failed to commit changeset for map {map_id}: {e}")
                return False

        return True
    
    def _update_farm_maturity(self, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, List[Any]]):
        """更新农田成熟状态"""
        # 检查新创建的农田
        for x, y, tile_type in changeset["tile_changes"]:
            if tile_type == FARM_UNTILLED:
                self.farm_maturity_tracker[(x, y)] = current_tick
        
        # 检查农田是否成熟
        matured_farms = []
        for (x, y), creation_tick in list(self.farm_maturity_tracker.items()):
            if current_tick - creation_tick >= self.farm_mature_ticks:
                if world_grid[y][x] == FARM_UNTILLED:
                    world_grid[y][x] = FARM_MATURE
                    changeset["tile_changes"].append((x, y, FARM_MATURE))
                    matured_farms.append((x, y))
                    logger.info(f"Farm at ({x}, {y}) matured")
        
        # 移除已成熟的农田记录
        for farm_pos in matured_farms:
            if farm_pos in self.farm_maturity_tracker:
                del self.farm_maturity_tracker[farm_pos]