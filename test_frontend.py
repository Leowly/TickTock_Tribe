#!/usr/bin/env python3
"""
测试前端村民显示功能
"""
import requests
import json
import time

def test_frontend():
    """测试前端村民显示功能"""
    base_url = "http://localhost:16151"
    
    print("=== 测试前端村民显示功能 ===")
    
    # 1. 生成新地图
    print("1. 生成新地图...")
    map_data = {
        "name": "测试村民地图",
        "world": {"width": 100, "height": 100},
        "forest": {"seed_prob": 0.05, "iterations": 3, "birth_threshold": 2},
        "water": {"density": 0.001, "turn_prob": 0.1, "stop_prob": 0.005, "height_influence": 5.0}
    }
    
    response = requests.post(f"{base_url}/api/generate_map", json=map_data)
    if response.status_code != 201:
        print(f"❌ 生成地图失败: {response.status_code}")
        return
    
    result = response.json()
    map_id = result["map_id"]
    print(f"✅ 地图生成成功，ID: {map_id}")
    
    # 2. 启动模拟
    print("2. 启动模拟...")
    response = requests.post(f"{base_url}/api/maps/{map_id}/start_simulation")
    if response.status_code != 200:
        print(f"❌ 启动模拟失败: {response.status_code}")
        return
    
    print("✅ 模拟启动成功")
    
    # 3. 等待几个tick让村民系统初始化
    print("3. 等待村民系统初始化...")
    time.sleep(3)
    
    # 4. 检查村民数据
    print("4. 检查村民数据...")
    response = requests.get(f"{base_url}/api/maps/{map_id}/villagers")
    if response.status_code != 200:
        print(f"❌ 获取村民数据失败: {response.status_code}")
        return
    
    villager_data = response.json()
    villagers = villager_data.get("villagers", [])
    houses = villager_data.get("houses", [])
    
    print(f"✅ 村民数据获取成功:")
    print(f"   - 村民数量: {len(villagers)}")
    print(f"   - 房屋数量: {len(houses)}")
    
    if villagers:
        print("   村民详情:")
        for villager in villagers:
            print(f"    - {villager['name']} ({villager['gender']}), 年龄: {villager['age']}岁, 饥饿度: {villager['hunger']}")
    
    # 5. 检查地图数据
    print("5. 检查地图数据...")
    response = requests.get(f"{base_url}/api/maps/{map_id}")
    if response.status_code != 200:
        print(f"❌ 获取地图数据失败: {response.status_code}")
        return
    
    map_info = response.json()
    print(f"✅ 地图数据获取成功:")
    print(f"   - 地图大小: {map_info['width']}x{map_info['height']}")
    print(f"   - 数据大小: {len(map_info['tiles_base64'])} 字符")
    
    # 6. 检查模拟状态
    print("6. 检查模拟状态...")
    response = requests.get(f"{base_url}/api/maps/{map_id}/simulation_status")
    if response.status_code == 200:
        status = response.json()
        print(f"✅ 模拟状态: 运行中={status['is_running']}, 当前tick={status['current_tick']}")
    
    # 7. 提供前端访问链接
    print("\n=== 前端访问信息 ===")
    print(f"🌐 地图查看器: {base_url}/view_map/{map_id}")
    print("📋 使用说明:")
    print("   - 在地图上可以看到村民（圆形）和房屋（方形）")
    print("   - 男性村民显示为红色，女性为青色")
    print("   - 儿童显示为黄色，老年为灰色")
    print("   - 房屋显示为棕色，显示居住人数")
    print("   - 放大可以看到村民的详细信息")
    print("   - 饥饿度低于30%的村民会显示红色警告")
    
    return map_id

if __name__ == "__main__":
    try:
        map_id = test_frontend()
        if map_id:
            print(f"\n🎉 测试完成！地图ID: {map_id}")
            print("现在可以在浏览器中查看村民系统了！")
        else:
            print("\n❌ 测试失败")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc() 