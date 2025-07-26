# core/ticker.py
import threading
import time
import logging
from typing import Dict, Optional
from core.world_updater import world_updater_instance

logger = logging.getLogger(__name__)

class Ticker:
    """
    管理基于时间的模拟循环。
    """
    def __init__(self, tick_interval: float = 1.0, inactivity_timeout: float = 2.0): # 添加超时参数
        self.tick_interval = tick_interval
        self.inactivity_timeout = inactivity_timeout # 存储超时时间
        self.active_maps: Dict[int, int] = {} # map_id -> current_tick
        self.last_activity: Dict[int, float] = {} # map_id -> last activity timestamp (添加这行)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None # 使用 Optional

    def start_simulation(self, map_id: int):
        """为指定地图启动模拟"""
        with self._lock:
            if map_id not in self.active_maps:
                self.active_maps[map_id] = 0 # 初始化 tick 为 0
                self.last_activity[map_id] = time.time() # 记录初始活动时间 (添加这行)
                logger.info(f"Ticker: Started simulation for map {map_id}")
                self._ensure_thread_running()

    def stop_simulation(self, map_id: int):
        """为指定地图停止模拟"""
        with self._lock:
            if map_id in self.active_maps:
                del self.active_maps[map_id]
                del self.last_activity[map_id] # 删除活动时间记录 (添加这行)
                logger.info(f"Ticker: Stopped simulation for map {map_id}")
                # 如果没有活跃地图，可以考虑停止线程（简化处理，让线程自己检查）

    def is_simulation_running(self, map_id: int) -> bool:
        """检查指定地图的模拟是否正在运行"""
        with self._lock:
            return map_id in self.active_maps

    def update_activity(self, map_id: int):
        """更新指定地图的最后活动时间"""
        with self._lock:
            if map_id in self.active_maps: # 只有正在模拟的地图才更新活动时间
                 self.last_activity[map_id] = time.time()
                 logger.debug(f"Ticker: Updated activity for map {map_id}")

    def _ensure_thread_running(self):
        """确保后台模拟线程正在运行"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("Ticker: Started background simulation thread.")

    def _run_loop(self):
        """后台模拟循环"""
        while self._running:
            current_time = time.time() # 获取当前时间 (添加这行)
            # 获取当前需要更新的地图列表副本
            with self._lock:
                 maps_to_update = list(self.active_maps.keys())
            
            # --- 检查并停止不活跃的模拟 (添加这部分) ---
            inactive_maps = []
            with self._lock:
                for map_id, last_time in self.last_activity.items():
                    if current_time - last_time > self.inactivity_timeout:
                        inactive_maps.append(map_id)
                        logger.info(f"Ticker: Map {map_id} timed out due to inactivity. Stopping simulation.")
            
            for map_id in inactive_maps:
                self.stop_simulation(map_id) # 停止超时的模拟
            # --- 检查结束 ---
            
            if not maps_to_update:
                # 如果没有地图需要更新，短暂休眠并继续检查
                time.sleep(self.tick_interval)
                continue
            # 等待一个 tick 间隔
            time.sleep(self.tick_interval)
            # 对每个活跃地图执行更新
            with self._lock: # 再次加锁以获取最新的 tick 值
                for map_id in maps_to_update:
                    if map_id in self.active_maps: # 再次检查，防止在 sleep 期间被移除
                        current_tick = self.active_maps[map_id]
                        # 调用世界更新逻辑
                        success = world_updater_instance.update(map_id, current_tick)
                        if success:
                            # 更新 tick 计数
                            self.active_maps[map_id] += 1
                            logger.debug(f"Ticker: Tick {current_tick + 1} completed for map {map_id}")
                        else:
                            logger.error(f"Ticker: Update failed for map {map_id} at tick {current_tick}. Stopping simulation.")
                            self.stop_simulation(map_id) # 如果更新失败，停止模拟
        logger.info("Ticker: Background simulation thread stopped.")

    def shutdown(self):
        """关闭 ticker"""
        self._running = False
        # 注意：Python 线程无法轻易强制停止，通常等待其自然结束或使用标志位。
        # 这里我们只是设置标志位，线程会在下一次循环检查时退出。
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2) # 等待最多2秒
            if self._thread.is_alive():
                logger.warning("Ticker: Simulation thread did not stop gracefully.")

# 创建全局 ticker 实例，设置2秒超时
ticker_instance = Ticker(tick_interval=1.0, inactivity_timeout=2.0) 
