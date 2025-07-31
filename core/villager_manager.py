# core/villager_manager.py
import random
import math
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, fields
from enum import Enum

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
    PLANT_TREE = "plant_tree"
    STORE_RESOURCES = "store_resources"
    TAKE_FOOD_FROM_HOUSE = "take_food_from_house"

@dataclass
class Villager:
    id: int
    name: str
    gender: str
    age: int
    age_in_ticks: int
    x: int
    y: int
    house_id: Optional[int]
    hunger: int
    food: int
    wood: int
    seeds: int
    status: VillagerStatus
    current_task: Optional[str]
    task_progress: int
    last_reproduction_tick: int
    is_alive: bool = True

@dataclass
class House:
    id: int
    x: int
    y: int
    capacity: int
    current_occupants: List[int]
    food_storage: int
    wood_storage: int
    seeds_storage: int
    build_tick: int
    is_standing: bool = True

class VillagerManager:
    """村民管理系统"""
    
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
        self.initial_seeds = villager_cfg.get('initial_seeds', 0)
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 25)
        self.max_hunger = villager_cfg.get('max_hunger', 100)
        self.ticks_to_starve = villager_cfg.get('ticks_to_starve', 5)
        self.hunger_per_food = villager_cfg.get('hunger_per_food', 25)
        self.ticks_per_year = villager_cfg.get('ticks_per_year', 365)
        self.max_age = villager_cfg.get('max_age', 100)
        self.elderly_age = villager_cfg.get('elderly_age', 65)
        self.child_age = villager_cfg.get('child_age', 6)
        self.adult_age = villager_cfg.get('adult_age', 18)
        self.death_probability_base = villager_cfg.get('death_probability_base', 0.001)
        self.death_probability_peak_age = villager_cfg.get('death_probability_peak_age', 80)
        self.death_probability_peak = villager_cfg.get('death_probability_peak', 0.1)
        self.reproduction_cooldown_ticks = villager_cfg.get('reproduction_cooldown_ticks', 360)
        self.reproduction_food_cost = villager_cfg.get('reproduction_food_cost', 20)
        self.reproduction_age_min = villager_cfg.get('reproduction_age_min', 18)
        self.reproduction_age_max = villager_cfg.get('reproduction_age_max', 45)
        self.reproduction_age_diff_max = villager_cfg.get('reproduction_age_diff_max', 10)
        self.reproduction_chance = villager_cfg.get('reproduction_chance', 0.1)
        self.task_durations = {
            TaskType.BUILD_FARMLAND: tasks_cfg.get('build_farmland_ticks', 10),
            TaskType.HARVEST_FARM: tasks_cfg.get('harvest_farm_ticks', 5),
            TaskType.CHOP_TREE: tasks_cfg.get('chop_tree_ticks', 10),
            TaskType.BUILD_HOUSE: tasks_cfg.get('build_house_ticks', 50),
            TaskType.PLANT_TREE: tasks_cfg.get('plant_tree_ticks', 5),
            TaskType.STORE_RESOURCES: 1,
            TaskType.TAKE_FOOD_FROM_HOUSE: 1,
        }
        self.chop_tree_wood_gain = tasks_cfg.get('chop_tree_wood_gain', 10)
        self.chop_tree_seeds_gain = tasks_cfg.get('chop_tree_seeds_gain', 20)
        self.plant_tree_seeds_cost = tasks_cfg.get('plant_tree_seeds_cost', 10)
        self.build_house_wood_cost = tasks_cfg.get('build_house_wood_cost', 30)
        self.farm_mature_ticks = farming_cfg.get('farm_mature_ticks', 30)
        self.farm_water_distance = farming_cfg.get('farm_water_distance', 2)
        self.farm_yield = farming_cfg.get('farm_yield', 60)
        self.house_capacity = housing_cfg.get('house_capacity', 4)
        self.house_decay_ticks = housing_cfg.get('house_decay_ticks', 10000)
        self.house_decay_probability = housing_cfg.get('house_decay_probability', 0.001)
        self.hunger_threshold = ai_cfg.get('hunger_threshold', 30)
        self.food_security_threshold = ai_cfg.get('food_security_threshold', 50)
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
    
    def create_initial_villagers(self, world_center_x: int, world_center_y: int) -> List[Villager]:
        male_villager = Villager(id=self.next_villager_id, name="Adam", gender="male", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x - 1, y=world_center_y, house_id=None, hunger=self.max_hunger, food=self.initial_food, wood=self.initial_wood, seeds=self.initial_seeds, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0)
        female_villager = Villager(id=self.next_villager_id + 1, name="Eve", gender="female", age=self.initial_age, age_in_ticks=self.initial_age * self.ticks_per_year, x=world_center_x + 1, y=world_center_y, house_id=None, hunger=self.max_hunger, food=self.initial_food, wood=self.initial_wood, seeds=self.initial_seeds, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0)
        self.villagers[male_villager.id] = male_villager
        self.villagers[female_villager.id] = female_villager
        self.next_villager_id += 2
        logger.info(f"Created initial villagers: {male_villager.name} and {female_villager.name}")
        return [male_villager, female_villager]

    def update_villagers(self, current_tick: int, world_grid: List[List[int]]) -> Dict[str, Any]:
        changeset: Dict[str, List[Any]] = {"villager_updates": [], "new_villagers": [], "deleted_villager_ids": [], "house_updates": [], "new_houses": [], "deleted_house_ids": [], "tile_changes": []}
        
        self.targeted_coords.clear()
        self._update_farm_maturity(current_tick, world_grid, changeset)
        
        villagers_to_process = list(self.villagers.values())
        random.shuffle(villagers_to_process)

        for villager in villagers_to_process:
            if not villager.is_alive: continue
                
            self._update_age_and_death(villager, changeset)
            if not villager.is_alive: continue

            self._update_hunger(villager, changeset)
            if not villager.is_alive: continue
            
            if villager.status == VillagerStatus.IDLE:
                self._decide_next_action(villager, world_grid)
            
            if villager.status == VillagerStatus.MOVING:
                self._process_movement(villager)
            elif villager.status == VillagerStatus.WORKING:
                self._process_task(villager, current_tick, world_grid, changeset)
            
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
        can_work = self._can_work(villager)
        if not can_work and villager.house_id:
            house = self.houses.get(villager.house_id)
            if house and house.food_storage > 0:
                food_consumed = 1 
                house.food_storage -= food_consumed
                villager.hunger = min(self.max_hunger, villager.hunger + food_consumed * self.hunger_per_food)
            else:
                 villager.hunger = max(0, villager.hunger - self.hunger_loss_per_tick)
        else:
            villager.hunger = max(0, villager.hunger - self.hunger_loss_per_tick)

        if villager.hunger < 80 and villager.food > 0:
            food_to_eat = min(villager.food, 1)
            villager.food -= food_to_eat
            villager.hunger = min(self.max_hunger, villager.hunger + food_to_eat * self.hunger_per_food)
        
        if villager.hunger <= 0:
            self._kill_villager(villager, changeset, "starved to death")

    def _kill_villager(self, villager: Villager, changeset: Dict[str, Any], reason: str):
        if not villager.is_alive: return
        logger.info(f"Villager {villager.name} (age {villager.age}) {reason}.")
        self._release_target_lock(villager)
        if villager.house_id and villager.house_id in self.houses:
            house = self.houses[villager.house_id]
            if villager.id in house.current_occupants:
                house.current_occupants.remove(villager.id)
        changeset["deleted_villager_ids"].append(villager.id)
        villager.is_alive = False

    def _can_work(self, villager: Villager, task_type: Optional[TaskType] = None) -> bool:
        age = villager.age
        if age < self.child_age or age > 80:
            return False
        if task_type in [TaskType.BUILD_HOUSE, TaskType.BUILD_FARMLAND]:
            if age < self.adult_age or age >= self.elderly_age:
                return False
        return True

    #--------- 开始修改 (增加大量日志) ---------
    def _decide_next_action(self, villager: Villager, world_grid: List[List[int]]):
        """全新的AI决策树，解决优先级问题，并增加详细调试日志"""
        log_prefix = f"[AI DEBUG Villager {villager.name} (ID: {villager.id})]"
        logger.debug(f"{log_prefix} --- Start Decision ---")

        if not self._can_work(villager):
            logger.debug(f"{log_prefix} Cannot Work (age: {villager.age}). No action taken.")
            return

        logger.debug(f"{log_prefix} Can Work: True")

        # 优先级 0: 资源管理
        logger.debug(f"{log_prefix} P0: Checking inventory... food={villager.food}, wood={villager.wood}, seeds={villager.seeds}")
        if villager.food > 0 or villager.wood > 0 or villager.seeds > 0:
            if villager.house_id and villager.house_id in self.houses:
                house = self.houses[villager.house_id]
                logger.debug(f"{log_prefix} P0: Has inventory and a house. Setting move task to STORE_RESOURCES at ({house.x}, {house.y}).")
                self._set_move_task(villager, TaskType.STORE_RESOURCES, (house.x, house.y))
                return
            else:
                logger.debug(f"{log_prefix} P0: Has inventory but no house to store. Skipping storage task.")
        
        # 优先级 1: 紧急生存
        logger.debug(f"{log_prefix} P1: Checking hunger... hunger={villager.hunger} (threshold={self.hunger_threshold})")
        if villager.hunger < self.hunger_threshold:
            logger.debug(f"{log_prefix} P1: Is hungry.")
            if villager.house_id and villager.house_id in self.houses:
                house = self.houses[villager.house_id]
                logger.debug(f"{log_prefix} P1: Checking house {house.id} for food... food_storage={house.food_storage}")
                if house.food_storage > 0:
                    logger.debug(f"{log_prefix} P1: House has food. Setting move task to TAKE_FOOD_FROM_HOUSE.")
                    self._set_move_task(villager, TaskType.TAKE_FOOD_FROM_HOUSE, (house.x, house.y))
                    return
            logger.debug(f"{log_prefix} P1: No food in house or no house. Finding food outside.")
            self._find_food_action(villager, world_grid)
            return
        
        # 优先级 2: 建立食物来源
        farm_count = self._count_farms(world_grid)
        logger.debug(f"{log_prefix} P2: Checking farm count... farms={farm_count} (required=2)")
        if farm_count < 2:
            logger.debug(f"{log_prefix} P2: Need more farms.")
            if self._can_work(villager, TaskType.BUILD_FARMLAND):
                logger.debug(f"{log_prefix} P2: Can build farm. Finding farmland site...")
                site = self._find_farmland_site(villager.x, villager.y, world_grid)
                if site:
                    logger.debug(f"{log_prefix} P2: Found site at {site}. Setting move task to BUILD_FARMLAND.")
                    self._set_move_task(villager, TaskType.BUILD_FARMLAND, site)
                    return
                else:
                    logger.debug(f"{log_prefix} P2: No suitable farmland site found.")
            else:
                logger.debug(f"{log_prefix} P2: Cannot build farm due to age restrictions.")
        
        # 优先级 3: 建立住所
        logger.debug(f"{log_prefix} P3: Checking housing... house_id={villager.house_id}")
        if not villager.house_id:
            logger.debug(f"{log_prefix} P3: Is homeless.")
            if self._can_work(villager, TaskType.BUILD_HOUSE):
                logger.debug(f"{log_prefix} P3: Checking wood for house... wood={villager.wood} (required={self.build_house_wood_cost})")
                if villager.wood >= self.build_house_wood_cost:
                    logger.debug(f"{log_prefix} P3: Has enough wood. Finding house site...")
                    site = self._find_house_site(villager.x, villager.y, world_grid)
                    if site:
                        logger.debug(f"{log_prefix} P3: Found site at {site}. Setting move task to BUILD_HOUSE.")
                        self._set_move_task(villager, TaskType.BUILD_HOUSE, site)
                        return
                    else:
                        logger.debug(f"{log_prefix} P3: No suitable house site found.")
                else:
                    logger.debug(f"{log_prefix} P3: Not enough wood. Finding a tree to chop...")
                    site = self._find_nearest_target(villager.x, villager.y, world_grid, FOREST)
                    if site:
                        logger.debug(f"{log_prefix} P3: Found tree at {site}. Setting move task to CHOP_TREE.")
                        self._set_move_task(villager, TaskType.CHOP_TREE, site)
                        return
                    else:
                        logger.debug(f"{log_prefix} P3: No trees found.")
            else:
                logger.debug(f"{log_prefix} P3: Cannot build house due to age restrictions.")

        # 优先级 4: 食物储备
        family_food = villager.food
        if villager.house_id and villager.house_id in self.houses:
            family_food += self.houses[villager.house_id].food_storage
        logger.debug(f"{log_prefix} P4: Checking food security... family_food={family_food} (security_threshold={self.food_security_threshold})")
        if family_food < self.food_security_threshold:
            logger.debug(f"{log_prefix} P4: Food is not secure. Finding food...")
            self._find_food_action(villager, world_grid)
            return

        # 优先级 5: 常规生产
        logger.debug(f"{log_prefix} P5: Food and housing are secure. Performing productive action...")
        self._productive_action(villager, world_grid)
        
        logger.debug(f"{log_prefix} --- End Decision: No action taken ---")
    #--------- 结束修改 ---------

    def _count_farms(self, world_grid: List[List[int]]) -> int:
        count = 0
        for y in range(len(world_grid)):
            for x in range(len(world_grid[0])):
                tile = world_grid[y][x]
                # Also count farms that are targeted for harvesting, as they will be replanted
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
    
    def _complete_task(self, villager: Villager, task_type: TaskType, x: int, y: int, world_grid: List[List[int]], changeset: Dict[str, Any], current_tick: int = 0):
        if task_type == TaskType.BUILD_FARMLAND:
            if world_grid[y][x] == PLAIN and self._is_near_water(x, y, world_grid):
                world_grid[y][x] = FARM_UNTILLED
                changeset["tile_changes"].append((x, y, FARM_UNTILLED))
                self.farm_maturity_tracker[(x, y)] = current_tick
        elif task_type == TaskType.HARVEST_FARM:
            if world_grid[y][x] == FARM_MATURE:
                world_grid[y][x] = FARM_UNTILLED
                changeset["tile_changes"].append((x, y, FARM_UNTILLED))
                villager.food += self.farm_yield
                self.farm_maturity_tracker[(x, y)] = current_tick
        elif task_type == TaskType.CHOP_TREE:
            if world_grid[y][x] == FOREST:
                world_grid[y][x] = PLAIN
                changeset["tile_changes"].append((x, y, PLAIN))
                villager.wood += self.chop_tree_wood_gain
                villager.seeds += self.chop_tree_seeds_gain
        elif task_type == TaskType.BUILD_HOUSE:
            if villager.wood >= self.build_house_wood_cost:
                villager.wood -= self.build_house_wood_cost
                house = self._create_house(x, y, current_tick)
                villager.house_id = house.id
                house.current_occupants.append(villager.id)
                changeset["new_houses"].append(house)
                logger.info(f"Villager {villager.name} built and moved into house {house.id}")
        elif task_type == TaskType.PLANT_TREE:
            if world_grid[y][x] == PLAIN and villager.seeds >= self.plant_tree_seeds_cost:
                villager.seeds -= self.plant_tree_seeds_cost
        elif task_type == TaskType.STORE_RESOURCES:
            if villager.house_id and villager.house_id in self.houses:
                house = self.houses[villager.house_id]
                house.food_storage += villager.food
                house.wood_storage += villager.wood
                house.seeds_storage += villager.seeds
                villager.food, villager.wood, villager.seeds = 0, 0, 0
        elif task_type == TaskType.TAKE_FOOD_FROM_HOUSE:
            if villager.house_id and villager.house_id in self.houses:
                house = self.houses[villager.house_id]
                food_to_take = min(house.food_storage, 20)
                if food_to_take > 0:
                    house.food_storage -= food_to_take
                    villager.food += food_to_take
    
    def _is_near_water(self, x: int, y: int, world_grid: List[List[int]]) -> bool:
        for dx in range(-self.farm_water_distance, self.farm_water_distance + 1):
            for dy in range(-self.farm_water_distance, self.farm_water_distance + 1):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and world_grid[ny][nx] == WATER):
                    return True
        return False
    
    def _create_house(self, x: int, y: int, build_tick: int) -> House:
        house = House(id=self.next_house_id, x=x, y=y, capacity=self.house_capacity, current_occupants=[], food_storage=0, wood_storage=0, seeds_storage=0, build_tick=build_tick, is_standing=True)
        self.houses[house.id] = house
        self.next_house_id += 1
        return house
    
    def _set_move_task(self, villager: Villager, task_type: TaskType, site: Tuple[int, int]) -> bool:
        target_x, target_y = site
        distance_sq = (villager.x - target_x)**2 + (villager.y - target_y)**2
        if distance_sq <= 10000:
            self.targeted_coords.add(site)
            villager.status = VillagerStatus.MOVING
            villager.current_task = f"move:{task_type.value}:{target_x},{target_y}"
            return True
        return False

    def _find_food_action(self, villager: Villager, world_grid: List[List[int]]):
        mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
        if mature_farm and self._set_move_task(villager, TaskType.HARVEST_FARM, mature_farm):
            return
        if self._can_work(villager, TaskType.BUILD_FARMLAND):
            farmland_site = self._find_farmland_site(villager.x, villager.y, world_grid)
            if farmland_site and self._set_move_task(villager, TaskType.BUILD_FARMLAND, farmland_site):
                return
    
    def _productive_action(self, villager: Villager, world_grid: List[List[int]]):
        actions = []
        if self._can_work(villager, TaskType.CHOP_TREE):
            actions.append((TaskType.CHOP_TREE, lambda: self._find_nearest_target(villager.x, villager.y, world_grid, FOREST)))
        if self._can_work(villager, TaskType.PLANT_TREE) and villager.seeds >= self.plant_tree_seeds_cost:
             actions.append((TaskType.PLANT_TREE, lambda: self._find_nearest_target(villager.x, villager.y, world_grid, PLAIN)))
        if self._can_work(villager, TaskType.BUILD_HOUSE) and villager.wood >= self.build_house_wood_cost:
            homeless_count = sum(1 for v in self.villagers.values() if v.is_alive and not v.house_id)
            if homeless_count > 0:
                 actions.append((TaskType.BUILD_HOUSE, lambda: self._find_house_site(villager.x, villager.y, world_grid)))
        if not actions: return
        random.shuffle(actions)
        task_type, finder_func = actions[0]
        site = finder_func()
        if site: self._set_move_task(villager, task_type, site)
    
    def _find_nearest_target(self, x: int, y: int, world_grid: List[List[int]], target_tile: int) -> Optional[Tuple[int, int]]:
        max_radius = 100
        for r in range(max_radius + 1):
            coords_to_check = set()
            for i in range(r + 1):
                j = r - i
                if i == 0 and j == 0: coords_to_check.add((x, y))
                else: coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])
            for nx, ny in sorted(list(coords_to_check)):
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid)):
                    if world_grid[ny][nx] == target_tile and (nx, ny) not in self.targeted_coords:
                        return (nx, ny)
        return None
    
    def _find_farmland_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        max_radius = 100
        for r in range(max_radius + 1):
            coords_to_check = set()
            for i in range(r + 1):
                j = r - i
                if i == 0 and j == 0: coords_to_check.add((x, y))
                else: coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])
            for nx, ny in sorted(list(coords_to_check)):
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
                if self._can_reproduce(male, female) and random.random() < self.reproduction_chance:
                    self._create_child(male, female, current_tick, changeset)
    
    def _can_reproduce(self, male: Villager, female: Villager) -> bool:
        if not (male.house_id and male.house_id == female.house_id): return False
        house = self.houses.get(male.house_id)
        if not house or len(house.current_occupants) >= house.capacity: return False
        total_food_cost = self.reproduction_food_cost * 2
        if house.food_storage < total_food_cost: return False
        return True
    
    def _create_child(self, male: Villager, female: Villager, current_tick: int, changeset: Dict[str, Any]):
        if male.house_id is None: return
        house = self.houses[male.house_id]
        house.food_storage -= self.reproduction_food_cost * 2
        child_gender = random.choice(["male", "female"])
        child_name = f"Child_{self.next_villager_id}"
        child = Villager(id=self.next_villager_id, name=child_name, gender=child_gender, age=0, age_in_ticks=0, x=male.x, y=male.y, house_id=male.house_id, hunger=self.max_hunger, food=0, wood=0, seeds=0, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0)
        self.villagers[child.id] = child
        self.next_villager_id += 1
        house.current_occupants.append(child.id)
        male.last_reproduction_tick = current_tick
        female.last_reproduction_tick = current_tick
        changeset["new_villagers"].append(child)
        logger.info(f"New child {child.name} born in house {house.id}")
    
    def _process_house_decay(self, current_tick: int, changeset: Dict[str, Any]):
        for house in list(self.houses.values()):
            if not house.is_standing: continue
            age_ticks = current_tick - house.build_tick
            if age_ticks > self.house_decay_ticks and random.random() < self.house_decay_probability:
                house.is_standing = False
                changeset["deleted_house_ids"].append(house.id)
                logger.info(f"House {house.id} collapsed")
    
    def get_villagers_data(self) -> List[Dict[str, Any]]:
        return [{"id": v.id, "name": v.name, "gender": v.gender, "age": v.age, "x": v.x, "y": v.y, "hunger": v.hunger, "status": v.status.value, "current_task": v.current_task, "house_id": v.house_id} for v in self.villagers.values() if v.is_alive]
    
    def get_houses_data(self) -> List[Dict[str, Any]]:
        return [{"id": h.id, "x": h.x, "y": h.y, "capacity": h.capacity, "occupants": len(h.current_occupants), "food_storage": h.food_storage, "is_standing": h.is_standing} for h in self.houses.values() if h.is_standing]