# core/config.py
import os
import toml
from typing import Dict, Any, Optional

class Config:
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置类。
        Args:
            config_path (Optional[str]): 配置文件的可选路径。如果为 None，则使用默认路径。
        """
        if config_path is None:
            # 从当前文件位置向上找到项目根目录，再定位到 config.toml
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, '..', 'config.toml')
        
        self.config_path: str = config_path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self):
        """从 .toml 文件加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.data = toml.load(f)
        except FileNotFoundError:
            print(f"警告：配置文件未找到于 {self.config_path}。将使用空配置或默认值。")
            self.data = {}

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """通用的 get 方法，用于获取顶层配置项"""
        return self.data.get(key, default or {})

    def get_world(self) -> Dict[str, Any]:
        """获取世界相关的配置"""
        return self.data.get('world', {})

    def get_forest(self) -> Dict[str, Any]:
        """获取森林相关的配置"""
        return self.data.get('forest', {})

    def get_water(self) -> Dict[str, Any]:
        """获取水域相关的配置"""
        return self.data.get('water', {})

    def get_view(self) -> Dict[str, Any]:
        """获取视图相关的配置"""
        return self.data.get('view', {})
    
    def get_villager(self) -> Dict[str, Any]:
        """获取村民相关的配置"""
        return self.data.get('villager', {})

    def get_time(self) -> Dict[str, Any]:
        """获取时间相关的配置"""
        return self.data.get('time', {})

    def get_tasks(self) -> Dict[str, Any]:
        """获取任务相关的配置"""
        return self.data.get('tasks', {})
    
    def get_farming(self) -> Dict[str, Any]:
        """获取农田相关的配置"""
        return self.data.get('farming', {})
    
    def get_housing(self) -> Dict[str, Any]:
        """获取房屋相关的配置"""
        return self.data.get('housing', {})
    
    def get_ai(self) -> Dict[str, Any]:
        """获取AI相关的配置"""
        return self.data.get('ai', {})