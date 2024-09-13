import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    @staticmethod
    def get_servers():
        servers = []
        i = 1
        while True:
            url = os.getenv(f"SERVER{i}_URL")
            api_key = os.getenv(f"SERVER{i}_API_KEY")
            if not url or not api_key:
                break
            servers.append({
                "name": f"server{i}",
                "url": url,
                "api_key": api_key
            })
            i += 1
        return servers

    SERVERS = get_servers()
    SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", 300))
    DB_PATH = os.getenv("DB_PATH", "dns_sync.db")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    ZONES_TO_SYNC = os.getenv("ZONES_TO_SYNC", "").split(",")
    ZONES_TO_SYNC = [zone.strip() for zone in ZONES_TO_SYNC if zone.strip()]
    
    SYNC_REVERSE_ZONES = os.getenv("SYNC_REVERSE_ZONES", "false").lower() == "true" 