# core/villager_manager.py
import random
import math
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
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
    gender: str  # 'male' or 'female'
    age: int  # 年龄（岁）
    age_in_ticks: int  # 年龄（tick）
    x: int  # 当前位置x
    y: int  # 当前位置y
    house_id: Optional[int]  # 居住的房屋ID
    hunger: int  # 饥饿度
    food: int  # 携带的食物
    wood: int  # 携带的木材
    seeds: int  # 携带的种子
    status: VillagerStatus
    current_task: Optional[str]  # 当前任务
    task_progress: int  # 任务进度
    last_reproduction_tick: int  # 上次繁殖的tick
    is_alive: bool = True

@dataclass
class House:
    """房屋数据结构"""
    id: int
    x: int
    y: int
    capacity: int
    current_occupants: List[int]  # 村民ID列表
    food_storage: int  # 房屋食物存储
    wood_storage: int  # 房屋木材存储
    seeds_storage: int  # 房屋种子存储
    build_tick: int  # 建造时间
    is_standing: bool = True

class VillagerManager:
    """村民管理系统"""
    
    def __init__(self, config: Any):
        self.config = config
        self.villagers: Dict[int, Villager] = {}
        self.houses: Dict[int, House] = {}
        self.next_villager_id = 1
        self.next_house_id = 1
        
        # 农田成熟时间跟踪
        self.farm_maturity_tracker = {}  # {(x, y): creation_tick}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载配置参数"""
        villager_cfg = self.config.get_villager()
        tasks_cfg = self.config.get_tasks()
        farming_cfg = self.config.get_farming()
        housing_cfg = self.config.get_housing()
        ai_cfg = self.config.get_ai()
        
        # 村民基础配置
        self.initial_age = villager_cfg.get('initial_age', 20)
        self.initial_food = villager_cfg.get('initial_food', 50)
        self.initial_wood = villager_cfg.get('initial_wood', 0)
        self.initial_seeds = villager_cfg.get('initial_seeds', 0)
        
        # 饥饿系统
        self.hunger_loss_per_tick = villager_cfg.get('hunger_loss_per_tick', 1)
        self.max_hunger = villager_cfg.get('max_hunger', 100)
        self.ticks_to_starve = villager_cfg.get('ticks_to_starve', 10)
        
        # 年龄系统
        self.ticks_per_year = villager_cfg.get('ticks_per_year', 365)
        self.max_age = villager_cfg.get('max_age', 100)
        self.elderly_age = villager_cfg.get('elderly_age', 65)
        self.child_age = villager_cfg.get('child_age', 6)
        self.adult_age = villager_cfg.get('adult_age', 18)
        
        # 死亡概率
        self.death_probability_base = villager_cfg.get('death_probability_base', 0.001)
        self.death_probability_peak_age = villager_cfg.get('death_probability_peak_age', 80)
        self.death_probability_peak = villager_cfg.get('death_probability_peak', 0.1)
        
        # 繁殖系统
        self.reproduction_cooldown_ticks = villager_cfg.get('reproduction_cooldown_ticks', 360)
        self.reproduction_food_cost = villager_cfg.get('reproduction_food_cost', 20)
        self.reproduction_age_min = villager_cfg.get('reproduction_age_min', 18)
        self.reproduction_age_max = villager_cfg.get('reproduction_age_max', 45)
        self.reproduction_age_diff_max = villager_cfg.get('reproduction_age_diff_max', 10)
        self.reproduction_chance = villager_cfg.get('reproduction_chance', 0.1)
        
        # 任务配置
        self.task_durations = {
            TaskType.BUILD_FARMLAND: tasks_cfg.get('build_farmland_ticks', 10),
            TaskType.HARVEST_FARM: tasks_cfg.get('harvest_farm_ticks', 5),
            TaskType.CHOP_TREE: tasks_cfg.get('chop_tree_ticks', 20),
            TaskType.BUILD_HOUSE: tasks_cfg.get('build_house_ticks', 50),
            TaskType.PLANT_TREE: tasks_cfg.get('plant_tree_ticks', 15)
        }
        
        # 任务产出
        self.chop_tree_wood_gain = tasks_cfg.get('chop_tree_wood_gain', 10)
        self.chop_tree_seeds_gain = tasks_cfg.get('chop_tree_seeds_gain', 20)
        self.plant_tree_seeds_cost = tasks_cfg.get('plant_tree_seeds_cost', 10)
        self.build_house_wood_cost = tasks_cfg.get('build_house_wood_cost', 20)
        
        # 农田配置
        self.farm_mature_ticks = farming_cfg.get('farm_mature_ticks', 30)
        self.farm_water_distance = farming_cfg.get('farm_water_distance', 2)
        self.farm_yield = farming_cfg.get('farm_yield', 15)
        
        # 房屋配置
        self.house_capacity = housing_cfg.get('house_capacity', 4)
        self.house_decay_ticks = housing_cfg.get('house_decay_ticks', 10000)
        self.house_decay_probability = housing_cfg.get('house_decay_probability', 0.001)
        
        # AI配置
        self.hunger_threshold = ai_cfg.get('hunger_threshold', 30)
        self.food_security_threshold = ai_cfg.get('food_security_threshold', 50)
        self.work_efficiency_child = ai_cfg.get('work_efficiency_child', 0.3)
        self.work_efficiency_elderly = ai_cfg.get('work_efficiency_elderly', 0.5)
    
    def load_from_database(self, snapshot):
        """从数据库快照加载村民和房屋数据"""
        # 清空当前数据
        self.villagers.clear()
        self.houses.clear()
        
        # 加载村民
        for villager_data in snapshot.villagers:
            villager = Villager(
                id=villager_data['id'],
                name=villager_data['name'],
                gender=villager_data['gender'],
                age=villager_data['age'],
                age_in_ticks=villager_data['age_in_ticks'],
                x=villager_data['x'],
                y=villager_data['y'],
                house_id=villager_data.get('house_id'),
                hunger=villager_data['hunger'],
                food=villager_data.get('food', 0),
                wood=villager_data.get('wood', 0),
                seeds=villager_data.get('seeds', 0),
                status=VillagerStatus(villager_data['status']),
                current_task=villager_data.get('current_task'),
                task_progress=villager_data.get('task_progress', 0),
                last_reproduction_tick=villager_data.get('last_reproduction_tick', 0),
                is_alive=villager_data.get('is_alive', True)
            )
            self.villagers[villager.id] = villager
            self.next_villager_id = max(self.next_villager_id, villager.id + 1)
        
        # 加载房屋
        for house_data in snapshot.houses:
            house = House(
                id=house_data['id'],
                x=house_data['x'],
                y=house_data['y'],
                capacity=house_data['capacity'],
                current_occupants=house_data['current_occupants'],
                food_storage=house_data.get('food_storage', 0),
                wood_storage=house_data.get('wood_storage', 0),
                seeds_storage=house_data.get('seeds_storage', 0),
                build_tick=house_data.get('build_tick', 0),
                is_standing=house_data.get('is_standing', True)
            )
            self.houses[house.id] = house
            self.next_house_id = max(self.next_house_id, house.id + 1)
    
    def create_initial_villagers(self, world_center_x: int, world_center_y: int) -> List[Villager]:
        """创建初始村民（一男一女）"""
        villagers = []
        
        # 创建男性村民
        male_villager = Villager(
            id=self.next_villager_id,
            name="Adam",
            gender="male",
            age=self.initial_age,
            age_in_ticks=self.initial_age * self.ticks_per_year,
            x=world_center_x,
            y=world_center_y,
            house_id=None,
            hunger=self.max_hunger,
            food=self.initial_food,
            wood=self.initial_wood,
            seeds=self.initial_seeds,
            status=VillagerStatus.IDLE,
            current_task=None,
            task_progress=0,
            last_reproduction_tick=0
        )
        
        # 创建女性村民
        female_villager = Villager(
            id=self.next_villager_id + 1,
            name="Eve",
            gender="female",
            age=self.initial_age,
            age_in_ticks=self.initial_age * self.ticks_per_year,
            x=world_center_x,
            y=world_center_y,
            house_id=None,
            hunger=self.max_hunger,
            food=self.initial_food,
            wood=self.initial_wood,
            seeds=self.initial_seeds,
            status=VillagerStatus.IDLE,
            current_task=None,
            task_progress=0,
            last_reproduction_tick=0
        )
        
        self.villagers[male_villager.id] = male_villager
        self.villagers[female_villager.id] = female_villager
        self.next_villager_id += 2
        
        logger.info(f"Created initial villagers: {male_villager.name} and {female_villager.name}")
        return [male_villager, female_villager]
    
    def update_villagers(self, current_tick: int, world_grid: List[List[int]]) -> Dict[str, Any]:
        """更新所有村民状态"""
        changeset = {
            "villager_updates": [],
            "new_villagers": [],
            "deleted_villager_ids": [],
            "house_updates": [],
            "new_houses": [],
            "deleted_house_ids": [],
            "tile_changes": []
        }
        
        # 更新农田成熟状态
        self._update_farm_maturity(current_tick, world_grid, changeset)
        
        villagers_to_process = list(self.villagers.values())
        
        for villager in villagers_to_process:
            if not villager.is_alive:
                continue
                
            # 更新年龄
            villager.age_in_ticks += 1
            villager.age = villager.age_in_ticks // self.ticks_per_year
            
            # 检查自然死亡
            if self._check_natural_death(villager):
                changeset["deleted_villager_ids"].append(villager.id)
                villager.is_alive = False
                continue
            
            # 更新饥饿度
            villager.hunger = max(0, villager.hunger - self.hunger_loss_per_tick)
            
            # 检查饿死
            if villager.hunger <= 0:
                changeset["deleted_villager_ids"].append(villager.id)
                villager.is_alive = False
                logger.info(f"Villager {villager.name} died of starvation")
                continue
            
            # 处理当前任务
            if villager.status == VillagerStatus.WORKING:
                self._process_task(villager, current_tick, world_grid, changeset)
            
            # 如果空闲，决定新任务
            if villager.status == VillagerStatus.IDLE:
                self._decide_next_action(villager, current_tick, world_grid, changeset)
            
            # 更新村民状态
            changeset["villager_updates"].append(villager)
        
        # 处理繁殖
        self._process_reproduction(current_tick, changeset)
        
        # 处理房屋倒塌
        self._process_house_decay(current_tick, changeset)
        
        return changeset
    
    def _update_farm_maturity(self, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
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
    
    def _check_natural_death(self, villager: Villager) -> bool:
        """检查自然死亡"""
        if villager.age >= self.max_age:
            return True
        
        if villager.age >= self.elderly_age:
            # 使用正态分布计算死亡概率
            age_diff = villager.age - self.elderly_age
            peak_diff = self.death_probability_peak_age - self.elderly_age
            
            # 简化的正态分布近似
            if age_diff <= peak_diff:
                death_prob = self.death_probability_base + (self.death_probability_peak - self.death_probability_base) * (age_diff / peak_diff)
            else:
                death_prob = self.death_probability_peak * math.exp(-(age_diff - peak_diff) / 10)
            
            return random.random() < death_prob
        
        return random.random() < self.death_probability_base
    
    def _process_task(self, villager: Villager, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
        """处理当前任务"""
        if not villager.current_task:
            villager.status = VillagerStatus.IDLE
            return
        
        task_parts = villager.current_task.split(':')
        task_type = TaskType(task_parts[0])
        target_coords = task_parts[1].split(',')
        target_x, target_y = int(target_coords[0]), int(target_coords[1])
        
        # 获取工作效率
        efficiency = self._get_work_efficiency(villager)
        
        # 推进任务进度
        villager.task_progress += int(efficiency)
        
        # 检查任务是否完成
        required_ticks = self.task_durations.get(task_type, 1)
        if villager.task_progress >= required_ticks:
            self._complete_task(villager, task_type, target_x, target_y, world_grid, changeset, current_tick)
            villager.status = VillagerStatus.IDLE
            villager.current_task = None
            villager.task_progress = 0
    
    def _get_work_efficiency(self, villager: Villager) -> float:
        """获取工作效率"""
        if villager.age < self.child_age or villager.age > 80:
            return 0.0  # 不能工作
        elif villager.age < self.adult_age or villager.age >= self.elderly_age:
            return self.work_efficiency_child if villager.age < self.adult_age else self.work_efficiency_elderly
        else:
            return 1.0  # 正常工作效率
    
    def _complete_task(self, villager: Villager, task_type: TaskType, x: int, y: int, world_grid: List[List[int]], changeset: Dict[str, Any], current_tick: int = 0):
        """完成任务"""
        if task_type == TaskType.BUILD_FARMLAND:
            if world_grid[y][x] == PLAIN and self._is_near_water(x, y, world_grid):
                world_grid[y][x] = FARM_UNTILLED
                changeset["tile_changes"].append((x, y, FARM_UNTILLED))
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
                logger.info(f"Villager {villager.name} chopped tree, gained {self.chop_tree_wood_gain} wood and {self.chop_tree_seeds_gain} seeds")
        
        elif task_type == TaskType.BUILD_HOUSE:
            if villager.wood >= self.build_house_wood_cost:
                villager.wood -= self.build_house_wood_cost
                # 从任务目标坐标获取current_tick
                house = self._create_house(x, y, current_tick)
                changeset["new_houses"].append(house)
                logger.info(f"Villager {villager.name} built house at ({x}, {y})")
        
        elif task_type == TaskType.PLANT_TREE:
            if world_grid[y][x] == PLAIN and villager.seeds >= self.plant_tree_seeds_cost:
                villager.seeds -= self.plant_tree_seeds_cost
                # 种树需要很长时间才能长成森林，这里先标记为特殊状态
                logger.info(f"Villager {villager.name} planted tree at ({x}, {y})")
    
    def _is_near_water(self, x: int, y: int, world_grid: List[List[int]]) -> bool:
        """检查是否靠近水"""
        for dx in range(-self.farm_water_distance, self.farm_water_distance + 1):
            for dy in range(-self.farm_water_distance, self.farm_water_distance + 1):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == WATER):
                    return True
        return False
    
    def _create_house(self, x: int, y: int, build_tick: int) -> House:
        """创建房屋"""
        house = House(
            id=self.next_house_id,
            x=x,
            y=y,
            capacity=self.house_capacity,
            current_occupants=[],
            food_storage=0,
            wood_storage=0,
            seeds_storage=0,
            build_tick=build_tick
        )
        self.houses[house.id] = house
        self.next_house_id += 1
        return house
    
    def _decide_next_action(self, villager: Villager, current_tick: int, world_grid: List[List[int]], changeset: Dict[str, Any]):
        """决定下一个行动"""
        # 如果饥饿，优先寻找食物
        if villager.hunger < self.hunger_threshold:
            self._find_food_action(villager, world_grid, changeset)
        # 如果食物充足，考虑其他活动
        elif villager.food > self.food_security_threshold:
            self._productive_action(villager, world_grid, changeset)
        # 否则继续寻找食物
        else:
            self._find_food_action(villager, world_grid, changeset)
    
    def _find_food_action(self, villager: Villager, world_grid: List[List[int]], changeset: Dict[str, Any]):
        """寻找食物的行动"""
        # 寻找成熟的农田
        mature_farm = self._find_nearest_mature_farm(villager.x, villager.y, world_grid)
        if mature_farm:
            villager.status = VillagerStatus.WORKING
            villager.current_task = f"{TaskType.HARVEST_FARM.value}:{mature_farm[0]},{mature_farm[1]}"
            villager.task_progress = 0
            return
        
        # 寻找可以建造农田的地方
        farmland_site = self._find_farmland_site(villager.x, villager.y, world_grid)
        if farmland_site:
            villager.status = VillagerStatus.WORKING
            villager.current_task = f"{TaskType.BUILD_FARMLAND.value}:{farmland_site[0]},{farmland_site[1]}"
            villager.task_progress = 0
            return
    
    def _productive_action(self, villager: Villager, world_grid: List[List[int]], changeset: Dict[str, Any]):
        """生产性活动"""
        # 随机选择活动
        actions = [
            (TaskType.CHOP_TREE, self._find_nearest_forest),
            (TaskType.BUILD_HOUSE, self._find_house_site),
            (TaskType.PLANT_TREE, self._find_planting_site)
        ]
        
        random.shuffle(actions)
        
        for task_type, finder_func in actions:
            site = finder_func(villager.x, villager.y, world_grid)
            if site:
                villager.status = VillagerStatus.WORKING
                villager.current_task = f"{task_type.value}:{site[0]},{site[1]}"
                villager.task_progress = 0
                return
    
    def _find_nearest_mature_farm(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        """寻找最近的成熟农田"""
        # 简化的最近搜索
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == FARM_MATURE):
                    return (nx, ny)
        return None
    
    def _find_farmland_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        """寻找农田建造地点"""
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == PLAIN and self._is_near_water(nx, ny, world_grid)):
                    return (nx, ny)
        return None
    
    def _find_nearest_forest(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        """寻找最近的森林"""
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == FOREST):
                    return (nx, ny)
        return None
    
    def _find_house_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        """寻找房屋建造地点"""
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == PLAIN):
                    return (nx, ny)
        return None
    
    def _find_planting_site(self, x: int, y: int, world_grid: List[List[int]]) -> Optional[Tuple[int, int]]:
        """寻找种树地点"""
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                nx, ny = x + dx, y + dy
                if (0 <= nx < len(world_grid[0]) and 0 <= ny < len(world_grid) and 
                    world_grid[ny][nx] == PLAIN):
                    return (nx, ny)
        return None
    
    def _process_reproduction(self, current_tick: int, changeset: Dict[str, Any]):
        """处理繁殖"""
        # 获取所有成年村民
        adults = [v for v in self.villagers.values() if v.is_alive and 
                 self.reproduction_age_min <= v.age <= self.reproduction_age_max]
        
        for male in adults:
            if male.gender != "male":
                continue
                
            for female in adults:
                if (female.gender != "female" or 
                    male.id == female.id or
                    abs(male.age - female.age) > self.reproduction_age_diff_max or
                    current_tick - male.last_reproduction_tick < self.reproduction_cooldown_ticks or
                    current_tick - female.last_reproduction_tick < self.reproduction_cooldown_ticks):
                    continue
                
                # 检查是否有足够的食物和房屋空间
                if self._can_reproduce(male, female):
                    if random.random() < self.reproduction_chance:
                        self._create_child(male, female, current_tick, changeset)
    
    def _can_reproduce(self, male: Villager, female: Villager) -> bool:
        """检查是否可以繁殖"""
        # 检查食物
        total_food = male.food + female.food
        if total_food < self.reproduction_food_cost * 2:  # 需要双倍食物
            return False
        
        # 检查房屋空间
        if male.house_id and female.house_id and male.house_id == female.house_id:
            house = self.houses.get(male.house_id)
            if house and len(house.current_occupants) < house.capacity:
                return True
        
        return False
    
    def _create_child(self, male: Villager, female: Villager, current_tick: int, changeset: Dict[str, Any]):
        """创建孩子"""
        # 消耗食物
        food_cost_per_parent = self.reproduction_food_cost
        male.food -= food_cost_per_parent
        female.food -= food_cost_per_parent
        
        # 创建孩子
        child_gender = random.choice(["male", "female"])
        child_name = f"Child_{self.next_villager_id}"
        
        child = Villager(
            id=self.next_villager_id,
            name=child_name,
            gender=child_gender,
            age=0,
            age_in_ticks=0,
            x=male.x,
            y=male.y,
            house_id=male.house_id,
            hunger=self.max_hunger,
            food=0,
            wood=0,
            seeds=0,
            status=VillagerStatus.IDLE,
            current_task=None,
            task_progress=0,
            last_reproduction_tick=0
        )
        
        self.villagers[child.id] = child
        self.next_villager_id += 1
        
        # 添加到房屋
        if male.house_id:
            house = self.houses.get(male.house_id)
            if house:
                house.current_occupants.append(child.id)
        
        # 更新繁殖时间
        male.last_reproduction_tick = current_tick
        female.last_reproduction_tick = current_tick
        
        changeset["new_villagers"].append(child)
        logger.info(f"New child {child.name} born to {male.name} and {female.name}")
    
    def _process_house_decay(self, current_tick: int, changeset: Dict[str, Any]):
        """处理房屋倒塌"""
        for house in list(self.houses.values()):
            if not house.is_standing:
                continue
            
            age_ticks = current_tick - house.build_tick
            if age_ticks > self.house_decay_ticks:
                if random.random() < self.house_decay_probability:
                    house.is_standing = False
                    changeset["deleted_house_ids"].append(house.id)
                    logger.info(f"House {house.id} collapsed")
    
    def get_villagers_data(self) -> List[Dict[str, Any]]:
        """获取村民数据用于前端显示"""
        return [
            {
                "id": v.id,
                "name": v.name,
                "gender": v.gender,
                "age": v.age,
                "x": v.x,
                "y": v.y,
                "hunger": v.hunger,
                "status": v.status.value,
                "current_task": v.current_task,
                "house_id": v.house_id
            }
            for v in self.villagers.values() if v.is_alive
        ]
    
    def get_houses_data(self) -> List[Dict[str, Any]]:
        """获取房屋数据用于前端显示"""
        return [
            {
                "id": h.id,
                "x": h.x,
                "y": h.y,
                "capacity": h.capacity,
                "occupants": len(h.current_occupants),
                "food_storage": h.food_storage,
                "is_standing": h.is_standing
            }
            for h in self.houses.values() if h.is_standing
        ] 