import logging
import time
import os
from technisync.config import config
from technisync.db_manager import DatabaseManager
from technisync.dns_client import TechnitiumDNSClient
from technisync.sync_manager import SyncManager
from technisync.utils import setup_logging

def main():
    setup_logging(config.LOG_LEVEL, log_file='technisync.log')
    logger = logging.getLogger(__name__)
    logger.info("Starting TechniSync")

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

    with DatabaseManager(config.DB_PATH) as db_manager:
        logger.info(f"Database initialized at {config.DB_PATH}")
        db_manager.check_and_create_tables()

        dns_clients = {server.name: TechnitiumDNSClient(server.url, server.api_key) for server in config.SERVERS}
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