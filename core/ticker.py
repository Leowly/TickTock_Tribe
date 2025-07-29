# core/ticker.py
import threading
import time
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class Ticker:
    """
    管理基于时间的模拟循环。
    通过依赖注入接收 world_updater。
    """
    def __init__(self, world_updater: Any, tick_interval: float = 1.0, inactivity_timeout: float = 2.0):
        """
        初始化 Ticker。
        Args:
            world_updater: 一个实现了 .update(map_id, tick) 方法的对象。
            tick_interval: 每个tick之间的秒数。
            inactivity_timeout: 模拟无活动自动停止的秒数。
        """
        self.world_updater = world_updater # 存储注入的依赖
        self.tick_interval = tick_interval
        self.inactivity_timeout = inactivity_timeout
        self.active_maps: Dict[int, int] = {}
        self.last_activity: Dict[int, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start_simulation(self, map_id: int):
        """为指定地图启动模拟"""
        with self._lock:
            if map_id not in self.active_maps:
                self.active_maps[map_id] = 0
                self.last_activity[map_id] = time.time()
                logger.info(f"Ticker: Started simulation for map {map_id}")
                self._ensure_thread_running()

    def stop_simulation(self, map_id: int):
        """为指定地图停止模拟"""
        with self._lock:
            if map_id in self.active_maps:
                del self.active_maps[map_id]
                if map_id in self.last_activity:
                    del self.last_activity[map_id]
                logger.info(f"Ticker: Stopped simulation for map {map_id}")

    def is_simulation_running(self, map_id: int) -> bool:
        """检查指定地图的模拟是否正在运行"""
        with self._lock:
            return map_id in self.active_maps
    
    def get_current_tick(self, map_id: int) -> int:
        """安全地获取指定地图的当前tick数。如果模拟未运行，则返回 -1。"""
        with self._lock:
            return self.active_maps.get(map_id, -1)

    def update_activity(self, map_id: int):
        """更新指定地图的最后活动时间"""
        with self._lock:
            if map_id in self.active_maps:
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
            current_time = time.time()
            
            inactive_maps_to_stop = []
            with self._lock:
                for map_id, last_time in list(self.last_activity.items()):
                    if current_time - last_time > self.inactivity_timeout:
                        inactive_maps_to_stop.append(map_id)
            
            if inactive_maps_to_stop:
                for map_id in inactive_maps_to_stop:
                    logger.info(f"Ticker: Map {map_id} timed out due to inactivity. Stopping simulation.")
                    self.stop_simulation(map_id)
            
            with self._lock:
                 maps_to_update = list(self.active_maps.keys())

            if not maps_to_update:
                time.sleep(self.tick_interval)
                continue
                
            time.sleep(self.tick_interval)

            with self._lock:
                for map_id in maps_to_update:
                    if map_id in self.active_maps:
                        current_tick = self.active_maps[map_id]
                        
                        # 使用注入的 world_updater 实例
                        success = self.world_updater.update(map_id, current_tick)
                        
                        if success:
                            self.active_maps[map_id] += 1
                            logger.debug(f"Ticker: Tick {current_tick + 1} completed for map {map_id}")
                        else:
                            logger.error(f"Ticker: Update failed for map {map_id} at tick {current_tick}. Stopping simulation.")
                            self.stop_simulation(map_id)
                            
        logger.info("Ticker: Background simulation thread stopped.")

    def shutdown(self):
        """关闭 ticker"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                logger.warning("Ticker: Simulation thread did not stop gracefully.")
