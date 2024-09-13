import logging
import time
from config import Config
from db_manager import DatabaseManager
from dns_client import TechnitiumDNSClient
from sync_manager import SyncManager

def setup_logging():
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), None)
    if not isinstance(log_level, int):
        raise ValueError(f"Invalid log level: {Config.LOG_LEVEL}")
    
    logging.basicConfig(level=log_level, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting TechniSync")

    db_manager = DatabaseManager(Config.DB_PATH)
    logger.info("Database initialized")

    dns_clients = {server['name']: TechnitiumDNSClient(server['url'], server['api_key']) 
                   for server in Config.SERVERS}
    sync_manager = SyncManager(Config, db_manager, dns_clients)

    while True:
        try:
            sync_manager.sync()
            logger.info(f"Sync completed. Waiting for {Config.SYNC_INTERVAL} seconds.")
            time.sleep(Config.SYNC_INTERVAL)
        except Exception as e:
            logger.error(f"Error during sync: {str(e)}", exc_info=True)
            time.sleep(60)  # retry timer? prolly need to remove

if __name__ == "__main__":
    main()