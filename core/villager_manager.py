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
    BUILD_FARMLAND = "build_farmland"
    HARVEST_FARM = "harvest_farm"
    CHOP_TREE = "chop_tree"
    BUILD_HOUSE = "build_house"
    PLANT_TREE = "plant_tree"
    FIND_FOOD = "find_food"

@dataclass
class Villager:
    """村民数据结构"""
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
    """房屋数据结构"""
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
        
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 1)
        self.max_hunger = villager_cfg.get('max_hunger', 100)
        self.ticks_to_starve = villager_cfg.get('ticks_to_starve', 10)
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
            TaskType.CHOP_TREE: tasks_cfg.get('chop_tree_ticks', 20),
            TaskType.BUILD_HOUSE: tasks_cfg.get('build_house_ticks', 50),
            TaskType.PLANT_TREE: tasks_cfg.get('plant_tree_ticks', 15)
        }
        
        self.chop_tree_wood_gain = tasks_cfg.get('chop_tree_wood_gain', 10)
        self.chop_tree_seeds_gain = tasks_cfg.get('chop_tree_seeds_gain', 20)
        self.plant_tree_seeds_cost = tasks_cfg.get('plant_tree_seeds_cost', 10)
        self.build_house_wood_cost = tasks_cfg.get('build_house_wood_cost', 20)
        
        self.farm_mature_ticks = farming_cfg.get('farm_mature_ticks', 30)
        self.farm_water_distance = farming_cfg.get('farm_water_distance', 2)
        self.farm_yield = farming_cfg.get('farm_yield', 15)
        
        self.house_capacity = housing_cfg.get('house_capacity', 4)
        self.house_decay_ticks = housing_cfg.get('house_decay_ticks', 10000)
        self.house_decay_probability = housing_cfg.get('house_decay_probability', 0.001)
        
        self.hunger_threshold = ai_cfg.get('hunger_threshold', 30)
        self.food_security_threshold = ai_cfg.get('food_security_threshold', 50)
        self.work_efficiency_child = ai_cfg.get('work_efficiency_child', 0.3)
        self.work_efficiency_elderly = ai_cfg.get('work_efficiency_elderly', 0.5)

    def load_from_database(self, snapshot):
        """【已修正】从数据库快照加载村民和房屋数据"""
        self.villagers.clear()
        self.houses.clear()

        # 获取dataclass中定义的所有字段名，用于过滤
        villager_fields = {f.name for f in fields(Villager)}
        house_fields = {f.name for f in fields(House)}

        for villager_data in snapshot.villagers:
            # 过滤掉数据库中多余的字段
            filtered_data = {k: v for k, v in villager_data.items() if k in villager_fields}
            # 确保status是枚举类型
            filtered_data['status'] = VillagerStatus(filtered_data['status'])
            
            villager = Villager(**filtered_data)
            self.villagers[villager.id] = villager
            self.next_villager_id = max(self.next_villager_id, villager.id + 1)
        
        for house_data in snapshot.houses:
            filtered_data = {k: v for k, v in house_data.items() if k in house_fields}
            # 确保occupants列表存在
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
        changeset = {"villager_updates": [], "new_villagers": [], "deleted_villager_ids": [], "house_updates": [], "new_houses": [], "deleted_house_ids": [], "tile_changes": []}
        
        self.targeted_coords.clear()

        self._update_farm_maturity(current_tick, world_grid, changeset)
        
        villagers_to_process = list(self.villagers.values())
        
        for villager in villagers_to_process:
            if not villager.is_alive: continue
                
            villager.age_in_ticks += 1
            villager.age = villager.age_in_ticks // self.ticks_per_year
            
            if self._check_natural_death(villager):
                self._release_target_lock(villager)
                changeset["deleted_villager_ids"].append(villager.id)
                villager.is_alive = False
                continue
            
            villager.hunger = max(0, villager.hunger - self.hunger_loss_per_tick)

            if villager.hunger < 80 and villager.food > 0:
                hunger_needed = self.max_hunger - villager.hunger
                food_to_eat = min(villager.food, (hunger_needed + self.hunger_per_food - 1) // self.hunger_per_food)
                if food_to_eat > 0:
                    villager.food -= food_to_eat
                    villager.hunger = min(self.max_hunger, villager.hunger + food_to_eat * self.hunger_per_food)
                    logger.debug(f"Villager {villager.name} ate {food_to_eat} food. Hunger: {villager.hunger}.")
            
            if villager.hunger <= 0:
                self._release_target_lock(villager)
                changeset["deleted_villager_ids"].append(villager.id)
                villager.is_alive = False
                logger.info(f"Villager {villager.name} died of starvation")
                continue
            
            if villager.status == VillagerStatus.MOVING:
                self._process_movement(villager, changeset)
            elif villager.status == VillagerStatus.WORKING:
                self._process_task(villager, current_tick, world_grid, changeset)
            
            if villager.status == VillagerStatus.IDLE:
                self._decide_next_action(villager, world_grid)
            
            changeset["villager_updates"].append(villager)
        
        self._process_reproduction(current_tick, changeset)
        self._process_house_decay(current_tick, changeset)
        
        return changeset
    
    def _release_target_lock(self, villager: Villager):
        if villager.current_task:
            try:
                parts = villager.current_task.split(':')
                coords_str = parts[-1]
                coords = tuple(map(int, coords_str.split(',')))
                if coords in self.targeted_coords:
                    self.targeted_coords.remove(coords)
                    logger.debug(f"Released target lock on {coords} for villager {villager.id}")
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
                    logger.info(f"Farm at ({x}, {y}) matured")
        
        for farm_pos in matured_farms:
            if farm_pos in self.farm_maturity_tracker:
                del self.farm_maturity_tracker[farm_pos]

    def _check_natural_death(self, villager: Villager) -> bool:
        if villager.age >= self.max_age:
            return True
        
        if villager.age >= self.elderly_age:
            age_diff = villager.age - self.elderly_age
            peak_diff = self.death_probability_peak_age - self.elderly_age
            
            if age_diff <= peak_diff:
                death_prob = self.death_probability_base + (self.death_probability_peak - self.death_probability_base) * (age_diff / peak_diff)
            else:
                death_prob = self.death_probability_peak * math.exp(-(age_diff - peak_diff) / 10)
            
            return random.random() < death_prob
        
        return random.random() < self.death_probability_base

    def _process_movement(self, villager: Villager, changeset: Dict[str, Any]):
        if not villager.current_task or not villager.current_task.startswith("move:"):
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            return

        try:
            parts = villager.current_task.split(':')
            final_task_name, coords_str = parts[1], parts[2]
            target_x, target_y = map(int, coords_str.split(','))
        except (IndexError, ValueError):
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            return

        villager.x, villager.y = target_x, target_y
        logger.info(f"Villager {villager.name} moved to ({target_x},{target_y}).")

        villager.status = VillagerStatus.WORKING
        villager.current_task = f"{final_task_name}:{target_x},{target_y}"
        villager.task_progress = 0

    def _process_task(self, villager: Villager, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
        if not villager.current_task:
            villager.status = VillagerStatus.IDLE
            return
        
        try:
            task_parts = villager.current_task.split(':')
            task_type, coords_str = TaskType(task_parts[0]), task_parts[1]
            target_x, target_y = map(int, coords_str.split(','))
        except (IndexError, ValueError):
             self._release_target_lock(villager)
             villager.status = VillagerStatus.IDLE
             villager.current_task = None
             return

        efficiency = self._get_work_efficiency(villager)
        villager.task_progress += int(efficiency)
        
        required_ticks = self.task_durations.get(task_type, 1)
        if villager.task_progress >= required_ticks:
            self._complete_task(villager, task_type, target_x, target_y, world_grid, changeset, current_tick)
            self._release_target_lock(villager)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            villager.task_progress = 0
    
    def _get_work_efficiency(self, villager: Villager) -> float:
        if villager.age < self.child_age or villager.age > 80:
            return 0.0
        elif villager.age < self.adult_age or villager.age >= self.elderly_age:
            return self.work_efficiency_child if villager.age < self.adult_age else self.work_efficiency_elderly
        else:
            return 1.0
    
    def _complete_task(self, villager: Villager, task_type: TaskType, x: int, y: int, world_grid: List[List[int]], changeset: Dict[str, Any], current_tick: int = 0):
        if task_type == TaskType.BUILD_FARMLAND:
            if world_grid[y][x] == PLAIN and self._is_near_water(x, y, world_grid):
                world_grid[y][x] = FARM_UNTILLED
                changeset["tile_changes"].append((x, y, FARM_UNTILLED))
                self.farm_maturity_tracker[(x, y)] = current_tick
                logger.info(f"Villager {villager.name} built farmland at ({x}, {y})")
        
        elif task_type == TaskType.HARVEST_FARM:
            if world_grid[y][x] == FARM_MATURE:
                world_grid[y][x] = PLAIN
                changeset["tile_changes"].append((x, y, PLAIN))
                villager.food += self.farm_yield
                logger.info(f"Villager {villager.name} harvested {self.farm_yield} food")
        
        elif task_type == TaskType.CHOP_TREE:
            if world_grid[y][x] == FOREST:
                world_grid[y][x] = PLAIN
                changeset["tile_changes"].append((x, y, PLAIN))
                villager.wood += self.chop_tree_wood_gain
                villager.seeds += self.chop_tree_seeds_gain
                logger.info(f"Villager {villager.name} chopped tree, gained wood and seeds")
        
        elif task_type == TaskType.BUILD_HOUSE:
            if villager.wood >= self.build_house_wood_cost:
                villager.wood -= self.build_house_wood_cost
                house = self._create_house(x, y, current_tick)
                changeset["new_houses"].append(house)
                logger.info(f"Villager {villager.name} built house at ({x}, {y})")
        
        elif task_type == TaskType.PLANT_TREE:
            if world_grid[y][x] == PLAIN and villager.seeds >= self.plant_tree_seeds_cost:
                villager.seeds -= self.plant_tree_seeds_cost
                logger.info(f"Villager {villager.name} planted tree at ({x}, {y})")
    
    def _is_near_water(self, x: int, y: int, world_grid: List[List[int]]) -> bool:
        for dx in range(-self.farm_water_distance, self.farm_water_distance + 1):
            for dy in range(-self.farm_water_distance, self.farm_water_distance + 1):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == WATER):
                    return True
        return False
    
    def _create_house(self, x: int, y: int, build_tick: int) -> House:
        house = House(id=self.next_house_id, x=x, y=y, capacity=self.house_capacity, current_occupants=[], food_storage=0, wood_storage=0, seeds_storage=0, build_tick=build_tick)
        self.houses[house.id] = house
        self.next_house_id += 1
        return house
    
    def _decide_next_action(self, villager: Villager, world_grid: List[List[int]]):
        if villager.hunger < self.hunger_threshold:
            self._find_food_action(villager, world_grid)
            return

        if villager.food >= self.food_security_threshold:
            self._productive_action(villager, world_grid)
            return
        
        self._find_food_action(villager, world_grid)

    def _set_move_task(self, villager: Villager, task_type: TaskType, site: Tuple[int, int]) -> bool:
        target_x, target_y = site
        distance_sq = (villager.x - target_x)**2 + (villager.y - target_y)**2
        
        if distance_sq <= 10000:
            self.targeted_coords.add(site)
            villager.status = VillagerStatus.MOVING
            villager.current_task = f"move:{task_type.value}:{target_x},{target_y}"
            logger.info(f"Villager {villager.name} locked target {site} for task {task_type.value}")
            return True
        return False

    def _find_food_action(self, villager: Villager, world_grid: List[List[int]]):
        mature_farm = self._find_nearest_target(villager.x, villager.y, world_grid, FARM_MATURE)
        if mature_farm and self._set_move_task(villager, TaskType.HARVEST_FARM, mature_farm):
            return

        farmland_site = self._find_farmland_site(villager.x, villager.y, world_grid)
        if farmland_site and self._set_move_task(villager, TaskType.BUILD_FARMLAND, farmland_site):
            return
    
    def _productive_action(self, villager: Villager, world_grid: List[List[int]]):
        actions = [(TaskType.CHOP_TREE, lambda x, y, wg: self._find_nearest_target(x, y, wg, FOREST)),
                   (TaskType.BUILD_HOUSE, self._find_house_site),
                   (TaskType.PLANT_TREE, lambda x, y, wg: self._find_nearest_target(x, y, wg, PLAIN))]
        random.shuffle(actions)
        
        for task_type, finder_func in actions:
            site = finder_func(villager.x, villager.y, world_grid)
            if site and self._set_move_task(villager, task_type, site):
                return
    
    def _find_nearest_target(self, x: int, y: int, world_grid: List[List[int]], target_tile: int) -> Optional[Tuple[int, int]]:
        max_radius = 100
        for r in range(max_radius + 1):
            for i in range(r + 1):
                j = r - i
                coords_to_check = set()
                if i == 0 and j == 0:
                    coords_to_check.add((x, y))
                else:
                    coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])
                
                for nx, ny in coords_to_check:
                    if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid)):
                        if world_grid[ny][nx] == target_tile and (nx, ny) not in self.targeted_coords:
                            return (nx, ny)
        return None
    
    def _find_farmland_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        max_radius = 100
        for r in range(max_radius + 1):
            for i in range(r + 1):
                j = r - i
                coords_to_check = set()
                if i == 0 and j == 0:
                    coords_to_check.add((x, y))
                else:
                    coords_to_check.update([(x + i, y + j), (x - i, y + j), (x + i, y - j), (x - i, y - j)])

                for nx, ny in coords_to_check:
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
        if (male.food + female.food) < self.reproduction_food_cost * 2:
            return False
        
        if male.house_id and male.house_id == female.house_id:
            house = self.houses.get(male.house_id)
            if house and len(house.current_occupants) < house.capacity:
                return True
        
        return False
    
    def _create_child(self, male: Villager, female: Villager, current_tick: int, changeset: Dict[str, Any]):
        male.food -= self.reproduction_food_cost
        female.food -= self.reproduction_food_cost
        
        child_gender = random.choice(["male", "female"])
        child_name = f"Child_{self.next_villager_id}"
        
        child = Villager(id=self.next_villager_id, name=child_name, gender=child_gender, age=0, age_in_ticks=0, x=male.x, y=male.y, house_id=male.house_id, hunger=self.max_hunger, food=0, wood=0, seeds=0, status=VillagerStatus.IDLE, current_task=None, task_progress=0, last_reproduction_tick=0)
        
        self.villagers[child.id] = child
        self.next_villager_id += 1
        
        if male.house_id:
            house = self.houses.get(male.house_id)
            if house:
                house.current_occupants.append(child.id)
        
        male.last_reproduction_tick = current_tick
        female.last_reproduction_tick = current_tick
        
        changeset["new_villagers"].append(child)
        logger.info(f"New child {child.name} born to {male.name} and {female.name}")
    
    def _process_house_decay(self, current_tick: int, changeset: Dict[str, Any]):
        for house in list(self.houses.values()):
            if not house.is_standing: continue
            
            age_ticks = current_tick - house.build_tick
            if age_ticks > self.house_decay_ticks and random.random() < self.house_decay_probability:
                house.is_standing = False
                changeset["deleted_house_ids"].append(house.id)
                logger.info(f"House {house.id} collapsed")
    
    def get_villagers_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": v.id, "name": v.name, "gender": v.gender, "age": v.age,
                "x": v.x, "y": v.y, "hunger": v.hunger, "status": v.status.value,
                "current_task": v.current_task, "house_id": v.house_id
            }
            for v in self.villagers.values() if v.is_alive
        ]
    
    def get_houses_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": h.id, "x": h.x, "y": h.y, "capacity": h.capacity,
                "occupants": len(h.current_occupants), "food_storage": h.food_storage,
                "is_standing": h.is_standing
            }
            for h in self.houses.values() if h.is_standing
        ]