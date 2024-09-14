import logging
import time
from config import config
from db_manager import DatabaseManager
from dns_client import TechnitiumDNSClient
from sync_manager import SyncManager

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

    db_manager = DatabaseManager(config.DB_PATH)
    logger.info("Database initialized")

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
            time.sleep(60)  # retry timer? prolly need to remove

if __name__ == "__main__":
    main()