import yaml
import os

class Config:
    def __init__(self, config_path='config.yaml'):
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)

        self.SERVERS = config['servers']
        self.SYNC_INTERVAL = config.get('sync_interval', 300)
        self.DB_PATH = config.get('db_path', 'dns_sync.db')
        self.LOG_LEVEL = config.get('log_level', 'INFO')
        self.SYNC_REVERSE_ZONES = config.get('sync_reverse_zones', False)
        self.ZONES_TO_SYNC = config.get('zones_to_sync', [])

    @classmethod
    def load(cls):
        config_path = os.environ.get('CONFIG_PATH', 'config.yaml')
        return cls(config_path)

config = Config.load()