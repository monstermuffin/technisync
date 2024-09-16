import yaml
import os
from .models import Server

class Config:
    def __init__(self, config_path='config.yaml'):
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as config_file:
                self.config = yaml.safe_load(config_file) or {}

        # env override
        self.SERVERS = self._get_servers()
        self.SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', self.config.get('sync_interval', 300)))
        
        self.DB_PATH = os.getenv('DB_PATH', './data/dns_sync.db')
        
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', self.config.get('log_level', 'INFO'))
        self.SYNC_REVERSE_ZONES = os.getenv('SYNC_REVERSE_ZONES', str(self.config.get('sync_reverse_zones', False))).lower() == 'true'
        self.ZONES_TO_SYNC = os.getenv('ZONES_TO_SYNC', ','.join(self.config.get('zones_to_sync', []))).split(',')
        self.ZONES_TO_SYNC = [zone.strip() for zone in self.ZONES_TO_SYNC if zone.strip()]

    def _get_servers(self):
        servers = []
        yaml_servers = self.config.get('servers', [])
        for server in yaml_servers:
            servers.append(Server(server['name'], server['url'], server['api_key']))

        i = 1
        while True:
            url = os.getenv(f"SERVER{i}_URL")
            api_key = os.getenv(f"SERVER{i}_API_KEY")
            if not url or not api_key:
                break
            server_name = f"server{i}"
            existing_server = next((s for s in servers if s.name == server_name), None)
            if existing_server:
                existing_server.url = url
                existing_server.api_key = api_key
            else:
                servers.append(Server(server_name, url, api_key))
            i += 1

        return servers

    @classmethod
    def load(cls):
        config_path = os.environ.get('CONFIG_PATH', 'config.yaml')
        return cls(config_path)

config = Config.load()