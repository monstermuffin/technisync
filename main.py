import logging
import time
import os
from technisync.config import config
from technisync.db_manager import DatabaseManager
from technisync.dns_client import TechnitiumDNSClient
from technisync.sync_manager import SyncManager

def setup_logging():
    log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
    if not isinstance(log_level, int):
        raise ValueError(f"Invalid log level: {config.LOG_LEVEL}")
    
    logging.basicConfig(level=log_level, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting TechniSync")

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

    db_manager = DatabaseManager(config.DB_PATH)
    logger.info(f"Database initialized at {config.DB_PATH}")

    dns_clients = {server['name']: TechnitiumDNSClient(server['url'], server['api_key']) 
                   for server in config.SERVERS}
    sync_manager = SyncManager(config, db_manager, dns_clients)

    while True:
        try:
            sync_manager.sync()
            logger.info(f"Sync completed. Waiting for {config.SYNC_INTERVAL} seconds.")
            time.sleep(config.SYNC_INTERVAL)
        except Exception as e:
            logger.error(f"Error during sync: {str(e)}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
