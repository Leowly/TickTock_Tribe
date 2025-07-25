import os
import toml

class Config:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config.toml')
        self.config_path = config_path
        self.data = {}
        self.load()

    def load(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.data = toml.load(f)

    def get_world(self):
        return self.data.get('world', {})

    def get_forest(self):
        return self.data.get('forest', {})

    def get_water(self):
        return self.data.get('water', {})

    def get_view(self):
        return self.data.get('view', {})
