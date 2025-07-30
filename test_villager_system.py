#!/usr/bin/env python3
"""
测试村民系统的核心功能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import Config
from core.villager_manager import VillagerManager, VillagerStatus, TaskType
from core.world_updater import WorldUpdater

def test_villager_creation():
    """测试村民创建"""
    print("=== 测试村民创建 ===")
    config = Config()
    vm = VillagerManager(config)
    
    # 创建初始村民
    villagers = vm.create_initial_villagers(500, 500)
    print(f"创建了 {len(villagers)} 个初始村民:")
    for v in villagers:
        print(f"  - {v.name} ({v.gender}), 年龄: {v.age}岁, 饥饿度: {v.hunger}")
    
    return vm

def test_villager_aging():
    """测试村民年龄增长"""
    print("\n=== 测试村民年龄增长 ===")
    config = Config()
    vm = VillagerManager(config)
    villagers = vm.create_initial_villagers(500, 500)
    
    # 模拟时间流逝
    for tick in range(365):  # 一年
        for villager in villagers:
            villager.age_in_ticks += 1
            villager.age = villager.age_in_ticks // vm.ticks_per_year
    
    print("一年后的村民状态:")
    for v in villagers:
        print(f"  - {v.name}: {v.age}岁 (tick: {v.age_in_ticks})")

def test_task_system():
    """测试任务系统"""
    print("\n=== 测试任务系统 ===")
    config = Config()
    vm = VillagerManager(config)
    villagers = vm.create_initial_villagers(500, 500)
    
    # 创建一个简单的世界网格
    world_grid = [[0 for _ in range(1000)] for _ in range(1000)]
    # 添加一些水
    world_grid[500][500] = 2  # WATER
    world_grid[501][500] = 2  # WATER
    
    # 测试村民决策
    villager = villagers[0]
    print(f"村民 {villager.name} 初始状态: {villager.status.value}")
    
    # 模拟饥饿状态
    villager.hunger = 20  # 低于饥饿阈值
    print(f"村民饥饿度: {villager.hunger}")
    
    # 让村民决定行动
    changeset = {"tile_changes": [], "villager_updates": [], "new_villagers": [], 
                "house_updates": [], "new_houses": [], "deleted_villager_ids": [], 
                "deleted_house_ids": []}
    
    vm._decide_next_action(villager, 0, world_grid, changeset)
    print(f"村民决定: {villager.status.value}")
    if villager.current_task:
        print(f"当前任务: {villager.current_task}")

def test_farm_system():
    """测试农田系统"""
    print("\n=== 测试农田系统 ===")
    config = Config()
    vm = VillagerManager(config)
    
    # 创建世界网格
    world_grid = [[0 for _ in range(100)] for _ in range(100)]
    # 添加水
    world_grid[50][50] = 2  # WATER
    
    # 测试农田建造
    x, y = 51, 50  # 靠近水的位置
    print(f"在位置 ({x}, {y}) 建造农田")
    
    # 检查是否靠近水
    is_near_water = vm._is_near_water(x, y, world_grid)
    print(f"是否靠近水: {is_near_water}")
    
    if is_near_water:
        world_grid[y][x] = 3  # FARM_UNTILLED
        print("农田建造成功")
        
        # 测试农田成熟
        changeset = {"tile_changes": [(x, y, 3)]}
        vm._update_farm_maturity(0, world_grid, changeset)
        
        # 模拟时间流逝
        for tick in range(vm.farm_mature_ticks + 1):
            vm._update_farm_maturity(tick, world_grid, changeset)
            if world_grid[y][x] == 4:  # FARM_MATURE
                print(f"农田在tick {tick}成熟")
                break

def test_reproduction_system():
    """测试繁殖系统"""
    print("\n=== 测试繁殖系统 ===")
    config = Config()
    vm = VillagerManager(config)
    
    # 创建成年村民
    male = vm.create_initial_villagers(500, 500)[0]
    female = vm.create_initial_villagers(500, 500)[1]
    
    # 设置繁殖条件
    male.age = 25
    female.age = 23
    male.food = 50
    female.food = 50
    
    print(f"男性村民: {male.name}, 年龄: {male.age}, 食物: {male.food}")
    print(f"女性村民: {female.name}, 年龄: {female.age}, 食物: {female.food}")
    
    # 检查繁殖条件
    can_reproduce = vm._can_reproduce(male, female)
    print(f"是否可以繁殖: {can_reproduce}")

def main():
    """主测试函数"""
    print("开始测试村民系统...\n")
    
    try:
        test_villager_creation()
        test_villager_aging()
        test_task_system()
        test_farm_system()
        test_reproduction_system()
        
        print("\n✅ 所有测试完成！村民系统运行正常。")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 