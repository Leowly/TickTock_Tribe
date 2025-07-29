# core/world_updater.py
import logging
from core import database, config
from core import villager_ai  # <-- 1. 导入新的AI模块

logger = logging.getLogger(__name__)

# 定义地形常量等
PLAIN = 0
FOREST = 1
WATER = 2
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
        
        # 预加载村民配置
        villager_cfg = self.config.get_villager()
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 1)
        
        # 2. 预加载任务耗时配置
        tasks_cfg = self.config.get('tasks', {}) # 假设config.py有get('tasks')
        self.task_durations = {
            'build_farmland': tasks_cfg.get('build_farmland_ticks', 10), # 示例：建农田要10 ticks
            'chop_tree': tasks_cfg.get('chop_tree_ticks', 20),
            'build_house': tasks_cfg.get('build_house_ticks', 50),
        }
        
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
        
        # 2. 准备一个空的变更集
        changeset = {
            "tile_changes": [], "villager_updates": [], "house_updates": [],
            "new_villagers": [], "new_houses": [], "deleted_villager_ids": [],
            "deleted_house_ids": []
        }
        
        # 3. 核心AI与模拟循环
        logger.debug(f"Simulating tick {current_tick} for map {map_id}...")
        
        villagers_to_process = list(snapshot.villagers)
        
        for villager in villagers_to_process:
            # --- 3a. AI决策与任务处理 ---
            
            # 如果村民是空闲的，为他决定新任务
            if villager['status'] == 'idle':
                # 调用AI模块进行决策
                action = villager_ai.decide_next_action(villager, snapshot, self.config.data)
                
                if action and action.get('type') == 'TASK':
                    task_name = action['name']
                    target_x, target_y = action['target']
                    
                    # 分配新任务
                    villager['status'] = 'working'
                    villager['current_task'] = f"{task_name}:{target_x},{target_y}"
                    villager['task_progress'] = 0
                    logger.info(f"Villager {villager['id']} starts task '{task_name}' at ({target_x},{target_y}).")

            # 如果村民在工作，推进任务进度
            elif villager['status'] == 'working':
                villager['task_progress'] += 1
                
                task_parts = villager['current_task'].split(':')
                task_name = task_parts[0]
                
                # 检查任务是否完成
                if villager['task_progress'] >= self.task_durations.get(task_name, 1):
                    logger.info(f"Villager {villager['id']} completes task '{task_name}'.")
                    
                    # 应用任务结果
                    if task_name == 'build_farmland':
                        target_coords = task_parts[1].split(',')
                        x, y = int(target_coords[0]), int(target_coords[1])
                        
                        # 检查地块是否仍然是平原，防止冲突
                        if snapshot.grid_2d[y][x] == PLAIN:
                            snapshot.grid_2d[y][x] = FARM_UNTILLED # 在内存中更新
                            changeset['tile_changes'].append((x, y, FARM_UNTILLED))
                            database.log_event(map_id, current_tick, 'TERRAIN_CHANGE', {'x': x, 'y': y, 'new_type': FARM_UNTILLED})
                    
                    # 重置村民状态，让他可以接受新任务
                    villager['status'] = 'idle'
                    villager['current_task'] = None
                    villager['task_progress'] = None

            # --- 3b. 被动状态更新 ---
            villager['age_in_ticks'] += 1
            if villager['hunger'] > 0:
                villager['hunger'] -= self.hunger_loss_per_tick
            
            if villager['hunger'] <= 0:
                logger.info(f"Villager {villager['id']} has died of starvation.")
                changeset["deleted_villager_ids"].append(villager['id'])
                continue

            # 将此村民的所有状态变更（包括AI驱动的和被动的）加入更新集
            changeset["villager_updates"].append(villager)

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