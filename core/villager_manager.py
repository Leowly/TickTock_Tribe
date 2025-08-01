# core/villager_manager.py
import random
import math
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, fields
from enum import Enum
from core import database

logger = logging.getLogger(__name__)

# 地形常量
PLAIN = 0
FOREST = 1
WATER = 2
FARM_UNTILLED = 3
FARM_MATURE = 4

class VillagerStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    MOVING = "moving"

class TaskType(Enum):
    HARVEST_FARM = "harvest_farm"
    CHOP_TREE = "chop_tree"
    BUILD_FARMLAND = "build_farmland"
    BUILD_HOUSE = "build_house"
    MOVE_TO_WATER = "move_to_water"
    MOVE_INTO_HOUSE = "move_into_house"

@dataclass
class Villager:
    id: int
    name: str
    gender: str
    age: int
    age_in_ticks: int
    x: int
    y: int
    house_id: int
    hunger: int
    status: VillagerStatus
    current_task: Optional[str]
    task_progress: int
    last_reproduction_tick: int
    is_alive: bool = True

@dataclass
class House:
    id: int
    x: Optional[int]
    y: Optional[int]
    capacity: int
    current_occupants: List[int]
    food_storage: int
    wood_storage: int
    seeds_storage: int
    build_tick: int
    is_standing: bool = True

class VillagerManager:
    def __init__(self, config: Any):
        self.config = config
        self.villagers: Dict[int, Villager] = {}
        self.houses: Dict[int, House] = {}
        self.next_villager_id = 1
        self.next_house_id = 1
        self.farm_maturity_tracker: Dict[Tuple[int, int], int] = {}
        self.targeted_coords: set[Tuple[int, int]] = set()
        self._load_config()
    
    def _load_config(self):
        villager_cfg = self.config.get_villager()
        tasks_cfg = self.config.get_tasks()
        farming_cfg = self.config.get_farming()
        housing_cfg = self.config.get_housing()
        ai_cfg = self.config.get_ai()
        self.initial_age = villager_cfg.get('initial_age', 20)
        self.initial_food = villager_cfg.get('initial_food', 50)
        self.initial_wood = villager_cfg.get('initial_wood', 0)
        self.initial_seeds = villager_cfg.get('initial_seeds', 5)
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 0.1)
        self.max_hunger = villager_cfg.get('max_hunger', 100)
        self.hunger_per_food = villager_cfg.get('hunger_per_food', 25)
        self.ticks_per_year = villager_cfg.get('ticks_per_year', 365)
        self.max_age = villager_cfg.get('max_age', 100)
        self.elderly_age = villager_cfg.get('elderly_age', 65)
        self.child_age = villager_cfg.get('child_age', 6)
        self.adult_age = villager_cfg.get('adult_age', 18)
        self.reproduction_cooldown_ticks = villager_cfg.get('reproduction_cooldown_ticks', 360)
        self.reproduction_food_cost = villager_cfg.get('reproduction_food_cost', 20)
        self.reproduction_age_min = villager_cfg.get('reproduction_age_min', 18)
        self.reproduction_age_max = villager_cfg.get('reproduction_age_max', 45)
        self.reproduction_age_diff_max = villager_cfg.get('reproduction_age_diff_max', 10)
        self.reproduction_chance = villager_cfg.get('reproduction_chance', 0.1)
        self.death_probability_base = villager_cfg.get('death_probability_base', 0.001)
        self.death_probability_peak_age = villager_cfg.get('death_probability_peak_age', 80)
        self.death_probability_peak = villager_cfg.get('death_probability_peak', 0.1)
        self.house_decay_ticks = housing_cfg.get('house_decay_ticks', 10000)
        self.house_decay_probability = housing_cfg.get('house_decay_probability', 0.001)
        self.task_durations = {
            TaskType.BUILD_FARMLAND: tasks_cfg.get('build_farmland_ticks', 20),
            TaskType.HARVEST_FARM: tasks_cfg.get('harvest_farm_ticks', 10),
            TaskType.CHOP_TREE: tasks_cfg.get('chop_tree_ticks', 15),
            TaskType.BUILD_HOUSE: tasks_cfg.get('build_house_ticks', 50),
            TaskType.MOVE_TO_WATER: 1,
        }
        self.chop_tree_wood_gain = tasks_cfg.get('chop_tree_wood_gain', 10)
        self.chop_tree_seeds_gain = tasks_cfg.get('chop_tree_seeds_gain', 5)
        self.build_house_wood_cost = housing_cfg.get('build_house_wood_cost', 30)
        self.farm_mature_ticks = farming_cfg.get('farm_mature_ticks', 100)
        self.farm_water_distance = farming_cfg.get('farm_water_distance', 3)
        self.farm_yield = farming_cfg.get('farm_yield', 40)
        self.hunger_threshold = ai_cfg.get('hunger_threshold', 40)
        self.food_security_threshold = ai_cfg.get('food_security_threshold', 60)
        self.work_efficiency_child = ai_cfg.get('work_efficiency_child', 0.3)
        self.work_efficiency_elderly = ai_cfg.get('work_efficiency_elderly', 0.5)

    def load_from_database(self, snapshot):
        self.villagers.clear()
        self.houses.clear()
        villager_fields = {f.name for f in fields(Villager)}
        house_fields = {f.name for f in fields(House)}
        for villager_data in snapshot.villagers:
            filtered_data = {k: v for k, v in villager_data.items() if k in villager_fields}
            filtered_data['status'] = VillagerStatus(filtered_data['status'])
            villager = Villager(**filtered_data)
            self.villagers[villager.id] = villager
            self.next_villager_id = max(self.next_villager_id, villager.id + 1)
        for house_data in snapshot.houses:
            filtered_data = {k: v for k, v in house_data.items() if k in house_fields}
            filtered_data['current_occupants'] = filtered_data.get('current_occupants', [])
            house = House(**filtered_data)
            self.houses[house.id] = house
            self.next_house_id = max(self.next_house_id, house.id + 1)

    def create_initial_villagers(self, world_center_x: int, world_center_y: int) -> List[Tuple[Villager, House]]:
        pairs = []
        adam_warehouse = House(id=-1, x=None, y=None, capacity=999, current_occupants=[], food_storage=self.initial_food, wood_storage=self.initial_wood, seeds_storage=self.initial_seeds, build_tick=0, is_standing=True)
        adam = Villager(id=-1, name="Adam", gender="male", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x - 1, y=world_center_y, house_id=-1, hunger=self.max_hunger, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0, is_alive=True)
        pairs.append((adam, adam_warehouse))
        
        eve_warehouse = House(id=-1, x=None, y=None, capacity=999, current_occupants=[], food_storage=self.initial_food, wood_storage=self.initial_wood, seeds_storage=self.initial_seeds, build_tick=0, is_standing=True)
        eve = Villager(id=-1, name="Eve", gender="female", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x + 1, y=world_center_y, house_id=-1, hunger=self.max_hunger, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0, is_alive=True)
        pairs.append((eve, eve_warehouse))

        logger.info(f"Prepared initial villager pairs for creation.")
        return pairs

    def update_villagers(self, current_tick: int, world_grid: List[List[int]]) -> Dict[str, Any]:
        """【新】引入优先级中断，允许村民在饥饿时放弃当前任务"""
        self.targeted_coords.clear()
        
        changeset: Dict[str, List[Any]] = {
            "tile_changes": [], "villager_updates": [], "house_updates": [], "new_villagers": [],
            "new_houses": [], "deleted_villager_ids": [], "deleted_house_ids": [],
            "build_and_move_requests": []
        }
        
        self._update_farm_maturity(current_tick, world_grid, changeset)
        
        villagers_to_process = list(self.villagers.values())
        random.shuffle(villagers_to_process)

        for villager in villagers_to_process:
            if not villager.is_alive: continue

            # 1. 先更新基础状态
            self._update_age_and_death(villager, changeset)
            if not villager.is_alive: continue
            self._update_hunger(villager, changeset)
            if not villager.is_alive: continue
            
            # --- 【核心修正】START: 优先级中断检查 ---
            # 检查村民是否处于饥饿的紧急状态
            is_in_emergency = villager.hunger < self.hunger_threshold
            
            # 检查当前任务是否是为了解决这个紧急状态（即，是否是去获取食物）
            is_handling_emergency = villager.current_task and ("HARVEST_FARM" in villager.current_task)

            # 如果处于紧急状态，但当前做的事情却不是为了解决它，则必须中断！
            if is_in_emergency and not is_handling_emergency and villager.status != VillagerStatus.IDLE:
                logger.debug(f"!!! INTERRUPT !!! Villager {villager.name} is critically hungry (hunger: {villager.hunger}). "
                             f"Stopping current task '{villager.current_task}' to find food.")
                
                self._release_target_lock(villager) # 释放旧任务占用的地块
                villager.status = VillagerStatus.IDLE
                villager.current_task = None
                villager.task_progress = 0
            # --- 【核心修正】END ---

            # 2. 根据村民的当前状态执行行动
            # 如果村民是空闲的（或者刚刚被中断任务变为空闲），则为他决策
            if villager.status == VillagerStatus.IDLE:
                self._decide_next_action(villager, world_grid)
            
            # 如果村民正在移动或工作，则继续处理
            if villager.status == VillagerStatus.MOVING:
                self._process_movement(villager)
            elif villager.status == VillagerStatus.WORKING:
                self._process_task(villager, current_tick, world_grid, changeset)
            
            # 确保村民的最新状态被记录
            if villager not in changeset["villager_updates"]:
                changeset["villager_updates"].append(villager)
        
        self._process_reproduction(current_tick, changeset)
        self._process_house_decay(current_tick, changeset)
        
        return changeset

    def _update_age_and_death(self, villager: Villager, changeset: Dict[str, Any]):
        villager.age_in_ticks += 1
        villager.age = villager.age_in_ticks // self.ticks_per_year
        if self._check_natural_death(villager):
            self._kill_villager(villager, changeset, "died of old age")

    def _update_hunger(self, villager: Villager, changeset: Dict[str, Any]):
        villager.hunger = max(0, villager.hunger - self.hunger_loss_per_tick)

        warehouse = self.houses.get(villager.house_id)
        if warehouse and villager.hunger <= (self.max_hunger - self.hunger_per_food):
            if warehouse.food_storage > 0:
                warehouse.food_storage -= 1
                villager.hunger = min(self.max_hunger, villager.hunger + self.hunger_per_food)
                if warehouse not in changeset["house_updates"]:
                    changeset["house_updates"].append(warehouse)

        if villager.hunger <= 0:
            self._kill_villager(villager, changeset, "starved to death")

    def _kill_villager(self, villager: Villager, changeset: Dict[str, Any], reason: str):
        if not villager.is_alive: return
        logger.info(f"Villager {villager.name} (age {villager.age}) {reason}.")
        self._release_target_lock(villager)
        
        warehouse = self.houses.get(villager.house_id)
        if warehouse:
            if villager.id in warehouse.current_occupants:
                warehouse.current_occupants.remove(villager.id)
                if warehouse not in changeset["house_updates"]:
                    changeset["house_updates"].append(warehouse)
            if warehouse.x is None and not warehouse.current_occupants:
                changeset["deleted_house_ids"].append(warehouse.id)

        changeset["deleted_villager_ids"].append(villager.id)
        villager.is_alive = False

    def _can_work(self, villager: Villager, task_type: Optional[TaskType] = None) -> bool:
        age = villager.age
        if age < self.child_age or age > 80: return False
        if task_type in [TaskType.BUILD_HOUSE, TaskType.BUILD_FARMLAND]:
            if age < self.adult_age or age >= self.elderly_age: return False
        return True

    # 位于 core/villager_manager.py 中
    def _decide_next_action(self, villager: Villager, world_grid: List[List[int]]):
        """
        【最终版】使用“意图锁定”来防止多个村民同时建房。
        """
        log_prefix = f"[AI DEBUG Villager {villager.name} (ID: {villager.id})]"
        if not self._can_work(villager): return
        
        warehouse = self.houses.get(villager.house_id)
        if not warehouse: return

        # ... (优先级 1, 2, 3: 求生、食物、农田 的逻辑保持不变) ...
        if villager.hunger < self.hunger_threshold:
            mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
            if mature_farm: self._set_move_task(villager, TaskType.HARVEST_FARM, mature_farm); return
        if warehouse.food_storage < self.food_security_threshold:
            mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
            if mature_farm: self._set_move_task(villager, TaskType.HARVEST_FARM, mature_farm); return
        population = len([v for v in self.villagers.values() if v.is_alive])
        farm_count = self._count_farms(world_grid)
        required_farms = math.ceil(population / 2.0) + 1
        if farm_count < required_farms and self._can_work(villager, TaskType.BUILD_FARMLAND):
            farmland_site = self._find_farmland_site(villager.x, villager.y, world_grid)
            if farmland_site: self._set_move_task(villager, TaskType.BUILD_FARMLAND, farmland_site); return
            else:
                water_site = self._find_nearest_target(villager.x, villager.y, world_grid, WATER)
                if water_site: self._set_move_task(villager, TaskType.MOVE_TO_WATER, water_site); return

        # --- 【核心修改】START: 全新住房决策 ---
        if warehouse.x is None: 
            vacant_house = self._find_vacant_house()
            if vacant_house and vacant_house.x is not None and vacant_house.y is not None:
                self._set_move_task(villager, TaskType.MOVE_INTO_HOUSE, (vacant_house.x, vacant_house.y))
                return

            house_count = len([h for h in self.houses.values() if h.x is not None and h.is_standing])
            required_houses = math.ceil(population / 3.0)

            # 【核心修正】使用新的“意图锁定”函数
            if house_count < required_houses and not self._is_house_build_intended():
                if self._can_work(villager, TaskType.BUILD_HOUSE):
                    if warehouse.wood_storage >= self.build_house_wood_cost:
                        site = self._find_house_site(villager.x, villager.y, world_grid)
                        if site:
                            self._set_move_task(villager, TaskType.BUILD_HOUSE, site)
                            return
                    else: 
                        site = self._find_nearest_target(villager.x, villager.y, world_grid, FOREST)
                        if site:
                            self._set_move_task(villager, TaskType.CHOP_TREE, site)
                            return
        # --- 【核心修改】END ---
        
        self._productive_action(villager, world_grid)

        # --- 【核心修改】START: 全新住房决策 ---
        if warehouse.x is None: 
            
            vacant_house = self._find_vacant_house()
            # --- 【核心修正】START: 增加安全检查 ---
            # 只有当找到的房子确实存在，并且它的坐标也存在时，才执行搬家
            if vacant_house and vacant_house.x is not None and vacant_house.y is not None:
                logger.debug(f"{log_prefix} Found a vacant house (ID: {vacant_house.id}). Moving in.")
                # 此处传递的坐标现在可以保证是 (int, int) 类型
                self._set_move_task(villager, TaskType.MOVE_INTO_HOUSE, (vacant_house.x, vacant_house.y))
                return
            # --- 【核心修正】END ---

            house_count = len([h for h in self.houses.values() if h.x is not None and h.is_standing])
            required_houses = math.ceil(population / 3.0)

            if house_count < required_houses and not self._is_house_build_in_progress():
                if self._can_work(villager, TaskType.BUILD_HOUSE):
                    if warehouse.wood_storage >= self.build_house_wood_cost:
                        site = self._find_house_site(villager.x, villager.y, world_grid)
                        if site:
                            self._set_move_task(villager, TaskType.BUILD_HOUSE, site)
                            return
                    else: 
                        site = self._find_nearest_target(villager.x, villager.y, world_grid, FOREST)
                        if site:
                            self._set_move_task(villager, TaskType.CHOP_TREE, site)
                            return
        
        self._productive_action(villager, world_grid)


    def _productive_action(self, villager: Villager, world_grid: List[List[int]]):
        possible_actions = []
        mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
        if mature_farm:
            possible_actions.append((TaskType.HARVEST_FARM, mature_farm))

        if self._can_work(villager, TaskType.CHOP_TREE):
            tree_site = self._find_nearest_target(villager.x, villager.y, world_grid, FOREST)
            if tree_site:
                possible_actions.append((TaskType.CHOP_TREE, tree_site))

        if not possible_actions:
            logger.debug(f"Villager {villager.name} has no productive actions available.")
            return

        random.shuffle(possible_actions)
        chosen_task, chosen_site = possible_actions[0]
        self._set_move_task(villager, chosen_task, chosen_site)

    def _complete_task(self, villager: Villager, task_type: TaskType, x: int, y: int, world_grid: List[List[int]], changeset: Dict[str, Any], current_tick: int = 0):
        """
        【最终版】将“搬家”也改为原子请求，彻底杜绝外键错误。
        """
        warehouse = self.houses.get(villager.house_id)
        if not warehouse: return

        # ... (处理 BUILD_FARMLAND, HARVEST_FARM, CHOP_TREE 的逻辑保持不变) ...
        if task_type == TaskType.MOVE_TO_WATER: return
        if task_type == TaskType.BUILD_FARMLAND:
            if world_grid[y][x] == PLAIN and self._is_near_water(x, y, world_grid):
                world_grid[y][x] = FARM_UNTILLED; changeset["tile_changes"].append((x, y, FARM_UNTILLED)); self.farm_maturity_tracker[(x, y)] = current_tick
        elif task_type == TaskType.HARVEST_FARM:
            if world_grid[y][x] == FARM_MATURE:
                world_grid[y][x] = FARM_UNTILLED; changeset["tile_changes"].append((x, y, FARM_UNTILLED)); warehouse.food_storage += self.farm_yield
                if warehouse not in changeset["house_updates"]: changeset["house_updates"].append(warehouse)
                self.farm_maturity_tracker[(x, y)] = current_tick
        elif task_type == TaskType.CHOP_TREE:
            if world_grid[y][x] == FOREST:
                world_grid[y][x] = PLAIN; changeset["tile_changes"].append((x, y, PLAIN)); warehouse.wood_storage += self.chop_tree_wood_gain; warehouse.seeds_storage += self.chop_tree_seeds_gain
                if warehouse not in changeset["house_updates"]: changeset["house_updates"].append(warehouse)
        
        # --- 【核心修改】START: 原子化“搬家”和“建房” ---
        elif task_type == TaskType.MOVE_INTO_HOUSE:
            found_house = None
            for h in self.houses.values():
                if h.x == x and h.y == y and h.is_standing:
                    found_house = h
                    break
            
            if found_house and len(found_house.current_occupants) < 3:
                # 提交一个“搬家”请求，包含（搬家者，旧仓库，目标房屋）
                changeset["move_in_requests"] = changeset.get("move_in_requests", [])
                changeset["move_in_requests"].append((villager, warehouse, found_house))
            else:
                logger.warning(f"Villager {villager.name} failed move-in attempt at ({x},{y}).")

        elif task_type == TaskType.BUILD_HOUSE:
            if warehouse.wood_storage >= self.build_house_wood_cost:
                new_house_blueprint = self._create_house(x, y, current_tick)
                warehouse.wood_storage -= self.build_house_wood_cost
                changeset["build_and_move_requests"].append((villager, new_house_blueprint, warehouse))
                if warehouse not in changeset["house_updates"]:
                    changeset["house_updates"].append(warehouse)
    
    def _create_child(self, male: Villager, female: Villager, current_tick: int, changeset: Dict[str, Any]):
        if male.house_id is None: return
        warehouse = self.houses.get(male.house_id)
        if not warehouse: return

        warehouse.food_storage -= self.reproduction_food_cost * 2
        
        child_gender = random.choice(["male", "female"])
        child_name = f"Child_{self.next_villager_id}"
        child = Villager(id=-1, name=child_name, gender=child_gender, age=0, age_in_ticks=0, x=female.x, y=female.y, house_id=male.house_id, hunger=self.max_hunger, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0, is_alive=True)
        
        warehouse.current_occupants.append(-1)
        
        male.last_reproduction_tick = current_tick
        female.last_reproduction_tick = current_tick
        
        changeset["new_villagers"].append(child)
        if warehouse not in changeset["house_updates"]:
            changeset["house_updates"].append(warehouse)
        if male not in changeset["villager_updates"]:
            changeset["villager_updates"].append(male)
        if female not in changeset["villager_updates"]:
            changeset["villager_updates"].append(female)
        
    def _can_reproduce(self, male: Villager, female: Villager) -> bool:
        if not (male.house_id and male.house_id == female.house_id): return False
        warehouse = self.houses.get(male.house_id)
        if not warehouse: return False
        total_food_cost = self.reproduction_food_cost * 2
        if warehouse.food_storage < total_food_cost: return False
        return True

    def _count_farms(self, world_grid: List[List[int]]) -> int:
        count = 0
        for y in range(len(world_grid)):
            for x in range(len(world_grid[0])):
                tile = world_grid[y][x]
                if tile in [FARM_UNTILLED, FARM_MATURE] or (x, y) in self.targeted_coords:
                     is_farm_task = False
                     for v in self.villagers.values():
                         if v.current_task and f":{x},{y}" in v.current_task and "HARVEST_FARM" in v.current_task:
                             is_farm_task = True
                             break
                     if not is_farm_task:
                        count +=1
        return count
    
    def _release_target_lock(self, villager: Villager):
        if villager.current_task:
            try:
                parts = villager.current_task.split(':')
                coords_str = parts[-1]
                x_str, y_str = coords_str.split(',')
                coords: Tuple[int, int] = (int(x_str), int(y_str))
                if coords in self.targeted_coords:
                    self.targeted_coords.remove(coords)
            except (ValueError, IndexError):
                pass

    def _update_farm_maturity(self, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
        matured_farms = []
        for (x, y), creation_tick in list(self.farm_maturity_tracker.items()):
            if current_tick - creation_tick >= self.farm_mature_ticks:
                if world_grid[y][x] == FARM_UNTILLED:
                    world_grid[y][x] = FARM_MATURE
                    changeset["tile_changes"].append((x, y, FARM_MATURE))
                    matured_farms.append((x, y))
        for farm_pos in matured_farms:
            if farm_pos in self.farm_maturity_tracker:
                del self.farm_maturity_tracker[farm_pos]

    def _check_natural_death(self, villager: Villager) -> bool:
        if villager.age >= self.max_age: return True
        if villager.age >= self.elderly_age:
            age_diff = villager.age - self.elderly_age
            peak_diff = self.death_probability_peak_age - self.elderly_age
            if peak_diff > 0 and age_diff <= peak_diff:
                death_prob = self.death_probability_base + (self.death_probability_peak - self.death_probability_base) * (age_diff / peak_diff)
            else:
                death_prob = self.death_probability_peak * math.exp(-(age_diff - peak_diff) / 10)
            return random.random() < death_prob
        return random.random() < self.death_probability_base

    def _process_movement(self, villager: Villager):
        if not villager.current_task or not villager.current_task.startswith("move:"):
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            return
        try:
            parts = villager.current_task.split(':')
            final_task_name, coords_str = parts[1], parts[2]
            x_str, y_str = coords_str.split(',')
            target_x, target_y = int(x_str), int(y_str)
        except (IndexError, ValueError):
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            return
        villager.x, villager.y = target_x, target_y
        villager.status = VillagerStatus.WORKING
        villager.current_task = f"{final_task_name}:{target_x},{target_y}"
        villager.task_progress = 0

    def _process_task(self, villager: Villager, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
        if not villager.current_task:
            villager.status = VillagerStatus.IDLE
            return
        try:
            task_parts = villager.current_task.split(':')
            task_type_str, coords_str = task_parts[0], task_parts[1]
            task_type = TaskType(task_type_str)
            x_str, y_str = coords_str.split(',')
            target_x, target_y = int(x_str), int(y_str)
        except (IndexError, ValueError):
             self._release_target_lock(villager)
             villager.status = VillagerStatus.IDLE
             villager.current_task = None
             return
        efficiency = self._get_work_efficiency(villager, task_type)
        villager.task_progress += int(efficiency) 
        required_ticks = self.task_durations.get(task_type, 1)
        if villager.task_progress >= required_ticks:
            self._complete_task(villager, task_type, target_x, target_y, world_grid, changeset, current_tick)
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            villager.task_progress = 0
    
    def _get_work_efficiency(self, villager: Villager, task_type: Optional[TaskType] = None) -> float:
        if not self._can_work(villager, task_type): return 0.0
        age = villager.age
        if age < self.adult_age: return self.work_efficiency_child
        if age >= self.elderly_age: return self.work_efficiency_elderly
        return 1.0
    
    def _is_near_water(self, x: int, y: int, world_grid: List[List[int]]) -> bool:
        for dx in range(-self.farm_water_distance, self.farm_water_distance + 1):
            for dy in range(-self.farm_water_distance, self.farm_water_distance + 1):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and world_grid[ny][nx] == WATER):
                    return True
        return False
    
    def _create_house(self, x: int, y: int, build_tick: int) -> House:
        house = House(id=-1, x=x, y=y, capacity=999, current_occupants=[], food_storage=0, wood_storage=0, seeds_storage=0, build_tick=build_tick, is_standing=True)
        return house
    
    def _set_move_task(self, villager: Villager, task_type: TaskType, site: Tuple[int, int]) -> bool:
        target_x, target_y = site
        self.targeted_coords.add(site)
        villager.status = VillagerStatus.MOVING
        villager.current_task = f"move:{task_type.value}:{target_x},{target_y}"
        return True

    def _find_food_action(self, villager: Villager, world_grid: List[List[int]]):
        mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
        if mature_farm and self._set_move_task(villager, TaskType.HARVEST_FARM, mature_farm):
            return
        if self._can_work(villager, TaskType.BUILD_FARMLAND):
            farmland_site = self._find_farmland_site(villager.x, villager.y, world_grid)
            if farmland_site and self._set_move_task(villager, TaskType.BUILD_FARMLAND, farmland_site):
                return
    
    def _find_nearest_target(self, x: int, y: int, world_grid: List[List[int]], target_tile: int) -> Optional[Tuple[int, int]]:
        max_radius = 250
        for r in range(max_radius + 1):
            coords_to_check = set()
            for i in range(r + 1):
                j = r - i
                if i == 0 and j == 0: coords_to_check.add((x, y))
                else: coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])
            
            coord_list = sorted(list(coords_to_check))
            random.shuffle(coord_list)
            for nx, ny in coord_list:
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid)):
                    if world_grid[ny][nx] == target_tile and (nx, ny) not in self.targeted_coords:
                        return (nx, ny)
        return None
    
    def _find_farmland_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        max_radius = 250
        for r in range(max_radius + 1):
            coords_to_check = set()
            for i in range(r + 1):
                j = r - i
                if i == 0 and j == 0: coords_to_check.add((x, y))
                else: coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])
            
            coord_list = sorted(list(coords_to_check))
            random.shuffle(coord_list)
            for nx, ny in coord_list:
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid)):
                    if world_grid[ny][nx] == PLAIN and (nx, ny) not in self.targeted_coords and self._is_near_water(nx, ny, world_grid):
                        return (nx, ny)
        return None

    def _find_house_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        return self._find_nearest_target(x, y, world_grid, PLAIN)
    
    def _process_reproduction(self, current_tick: int, changeset: Dict[str, Any]):
        adults = [v for v in self.villagers.values() if v.is_alive and 
                 self.reproduction_age_min <= v.age <= self.reproduction_age_max]
        for male in adults:
            if male.gender != "male": continue
            for female in adults:
                if (female.gender != "female" or male.id == female.id or
                    abs(male.age - female.age) > self.reproduction_age_diff_max or
                    current_tick - male.last_reproduction_tick < self.reproduction_cooldown_ticks or
                    current_tick - female.last_reproduction_tick < self.reproduction_cooldown_ticks):
                    continue
                if self._can_reproduce(male, female):
                    self._create_child(male, female, current_tick, changeset)
    
    def _process_house_decay(self, current_tick: int, changeset: Dict[str, Any]):
        """
        【新】在处理居民前，增加对None值的检查，确保代码健壮性。
        """
        houses_to_process = list(self.houses.values())
        for house in houses_to_process:
            if not house.is_standing or house.x is None: 
                continue

            age_ticks = current_tick - house.build_tick
            if age_ticks > self.house_decay_ticks and random.random() < self.house_decay_probability:
                logger.info(f"House {house.id} at ({house.x}, {house.y}) collapsed.")
                house.is_standing = False
                
                # 从字典中安全地获取居民对象列表
                residents_to_relocate = [self.villagers.get(vid) for vid in house.current_occupants]
                num_residents = len([res for res in residents_to_relocate if res is not None and res.is_alive])

                if num_residents > 0:
                    base_food, rem_food = divmod(house.food_storage, num_residents)
                    base_wood, rem_wood = divmod(house.wood_storage, num_residents)
                    base_seeds, rem_seeds = divmod(house.seeds_storage, num_residents)
                    
                    # 使用一个计数器来公平分配余数
                    resident_counter = 0 
                    for villager in residents_to_relocate:
                        # --- 【核心修正】START: 增加对None值的防御性检查 ---
                        # 在访问任何属性前，必须确保villager不是None且还活着
                        if not villager or not villager.is_alive:
                            continue
                        # --- 【核心修正】END ---
                        
                        food_share = base_food + 1 if resident_counter < rem_food else base_food
                        wood_share = base_wood + 1 if resident_counter < rem_wood else base_wood
                        seeds_share = base_seeds + 1 if resident_counter < rem_seeds else base_seeds
                        resident_counter += 1 # 增加计数器
                        
                        new_warehouse = House(id=-1, x=None, y=None, capacity=999, 
                                              current_occupants=[], 
                                              food_storage=food_share, 
                                              wood_storage=wood_share, 
                                              seeds_storage=seeds_share,
                                              build_tick=current_tick, is_standing=True)
                        
                        changeset["homeless_updates"] = changeset.get("homeless_updates", [])
                        changeset["homeless_updates"].append((villager, new_warehouse))
                        
                        logger.info(f"Villager {villager.name} is now homeless. New virtual warehouse created with assets: "
                                    f"Food({food_share}), Wood({wood_share}), Seeds({seeds_share}).")

                changeset["deleted_house_ids"].append(house.id)
    
    def get_villagers_data(self) -> List[Dict[str, Any]]:
        return [{"id": v.id, "name": v.name, "gender": v.gender, "age": v.age, "x": v.x, "y": v.y, "hunger": v.hunger, "status": v.status.value, "current_task": v.current_task, "house_id": v.house_id} for v in self.villagers.values() if v.is_alive]
    
    def get_houses_data(self) -> List[Dict[str, Any]]:
        return [{"id": h.id, "x": h.x, "y": h.y, "occupants": len(h.current_occupants), "food_storage": h.food_storage, "is_standing": h.is_standing} for h in self.houses.values() if h.is_standing and h.x is not None]
    
    def create_and_store_initial_villagers(self, map_id: int, width: int, height: int):
        """
        【新】这是一个全新的函数。
        它负责创建初始村民对象，并直接将它们原子化地写入数据库。
        这个函数取代了所有旧的在 tick 0 创建村民的逻辑。
        """
        world_center_x = width // 2
        world_center_y = height // 2

        # 1. 准备好村民和他们虚拟仓库的“蓝图”
        adam_warehouse_obj = House(id=-1, x=None, y=None, capacity=999, current_occupants=[], food_storage=self.initial_food, wood_storage=self.initial_wood, seeds_storage=self.initial_seeds, build_tick=0, is_standing=True)
        adam_obj = Villager(id=-1, name="Adam", gender="male", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x - 1, y=world_center_y, house_id=-1, hunger=self.max_hunger, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0, is_alive=True)
        
        eve_warehouse_obj = House(id=-1, x=None, y=None, capacity=999, current_occupants=[], food_storage=self.initial_food, wood_storage=self.initial_wood, seeds_storage=self.initial_seeds, build_tick=0, is_standing=True)
        eve_obj = Villager(id=-1, name="Eve", gender="female", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x + 1, y=world_center_y, house_id=-1, hunger=self.max_hunger, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0, is_alive=True)

        initial_pairs = [(adam_obj, adam_warehouse_obj), (eve_obj, eve_warehouse_obj)]
        
        # 2. 构造一个专门用于初始化的 changeset
        changeset = {
            "initial_creation_pairs": initial_pairs
        }

        # 3. 直接调用数据库的 commit_changes 函数来完成原子化写入
        database.commit_changes(map_id, changeset)

    def _is_house_build_in_progress(self) -> bool:
        """
        【新】检查当前是否有任何村民正在执行建造房屋的任务。
        这是实现“只派一个人去建房”的关键。
        """
        for villager in self.villagers.values():
            if villager.is_alive and villager.current_task and "BUILD_HOUSE" in villager.current_task:
                return True
        return False
    
# 请将这个新函数添加到 core/villager_manager.py 的 VillagerManager 类内部
    def _find_vacant_house(self) -> Optional[House]:
        """
        【新】寻找一个有空余位置的、已经建好的实体房屋。
        """
        # 我们对房屋进行随机化，避免所有村民都涌向同一个房子
        available_houses = [h for h in self.houses.values() if h.x is not None and h.is_standing]
        random.shuffle(available_houses)
        
        for house in available_houses:
            # 使用3作为容量，提供冗余
            if len(house.current_occupants) < 3:
                return house
        return None
    
    def _is_house_build_intended(self) -> bool:
        """
        【新】检查是否有任何村民已经“打算”去建房。
        这包括正在移动去建房，和正在建房的村民。
        """
        for villager in self.villagers.values():
            if villager.is_alive and villager.current_task:
                # 检查任务是否是 BUILD_HOUSE，无论他是正在移动还是正在工作
                if "BUILD_HOUSE" in villager.current_task:
                    return True
        return False