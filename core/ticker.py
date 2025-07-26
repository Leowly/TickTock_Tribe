# core/ticker.py
import threading
import time
import logging
from typing import Dict, Set ,Optional
from core.world_updater import world_updater_instance

logger = logging.getLogger(__name__)

class Ticker:
    """
    管理基于时间的模拟循环。
    """
    def __init__(self, tick_interval: float = 1.0): # 默认1秒 per tick
        self.tick_interval = tick_interval
        self.active_maps: Dict[int, int] = {} # map_id -> current_tick
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start_simulation(self, map_id: int):
        """为指定地图启动模拟"""
        with self._lock:
            if map_id not in self.active_maps:
                self.active_maps[map_id] = 0 # 初始化 tick 为 0
                logger.info(f"Ticker: Started simulation for map {map_id}")
                self._ensure_thread_running()

    def stop_simulation(self, map_id: int):
        """为指定地图停止模拟"""
        with self._lock:
            if map_id in self.active_maps:
                del self.active_maps[map_id]
                logger.info(f"Ticker: Stopped simulation for map {map_id}")
                # 如果没有活跃地图，可以考虑停止线程（简化处理，让线程自己检查）

    def is_simulation_running(self, map_id: int) -> bool:
        """检查指定地图的模拟是否正在运行"""
        with self._lock:
            return map_id in self.active_maps

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
            # 获取当前需要更新的地图列表副本
            with self._lock:
                 maps_to_update = list(self.active_maps.keys())

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
                        success = world_updater_instance.update_debug(map_id, current_tick)
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

# 创建全局 ticker 实例
ticker_instance = Ticker(tick_interval=1.0) # 可以根据需要调整间隔