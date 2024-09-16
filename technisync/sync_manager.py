import logging
import json
from datetime import datetime
import ipaddress

class SyncManager:
    def __init__(self, config, db_manager, dns_clients):
        self.config = config
        self.db_manager = db_manager
        self.dns_clients = dns_clients
        self.logger = logging.getLogger(__name__)
        self.changes = {server['name']: {} for server in config.SERVERS}
        # records not needed for repl
        self.excluded_record_types = [
            'SOA',      
            'NS',       
            'RRSIG',    # DNSSEC signature
            'NSEC',     # Next Secure record (for DNSSEC)
            'NSEC3',    # NSEC version 3 (for DNSSEC)
            'DNSKEY',   # DNS Public Key (for DNSSEC)
            'DS',       # Delegation Signer (for DNSSEC)
            'CDS',      # Child DS (for DNSSEC key rollovers)
            'CDNSKEY',  # Child DNSKEY (for DNSSEC key rollovers)
            'TSIG',     # Transaction Signature
            'TKEY',     # Transaction Key - used for key exchange
            'AXFR',     # Full zone transfer - might be required?
            'IXFR'      # Incremental zone transfer - might be required?
        ]

    def sync(self):
        synced_reverse_zones = set()
        for server in self.config.SERVERS:
            self.logger.info(f"Syncing records for server: {server['name']}")
            try:
                zones = self.dns_clients[server['name']].get_zones()
                for zone in zones.get('zones', []):
                    if self.should_sync_zone(zone['name']):
                        self.sync_zone(server['name'], zone['name'])
                        if self.is_reverse_zone(zone['name']):
                            synced_reverse_zones.add(zone['name'])
                
                if self.config.SYNC_REVERSE_ZONES:
                    self.sync_dhcp_scopes(server['name'], synced_reverse_zones)
            except Exception as e:
                self.logger.error(f"Error syncing server {server['name']}: {str(e)}", exc_info=True)

        self.propagate_changes()
        self.log_sync_summary()

    def sync_dhcp_scopes(self, server_name, synced_reverse_zones):
        try:
            dhcp_scopes = self.dns_clients[server_name].get_dhcp_scopes()
            for scope in dhcp_scopes.get('scopes', []):
                reverse_zone = self.get_reverse_zone_from_network(scope['networkAddress'], scope['subnetMask'])
                if reverse_zone and reverse_zone not in synced_reverse_zones:
                    for srv in self.config.SERVERS:
                        self.ensure_reverse_zone_exists(srv['name'], reverse_zone)
                    self.db_manager.set_zone_owner(reverse_zone, server_name)
                    self.sync_zone(server_name, reverse_zone)
                    synced_reverse_zones.add(reverse_zone)
        except Exception as e:
            self.logger.error(f"Error syncing DHCP scopes for server {server_name}: {str(e)}", exc_info=True)

    def should_sync_zone(self, zone_name):
        if self.is_internal_zone(zone_name):
            return False
        if not self.config.ZONES_TO_SYNC:
            return True 
        return zone_name in self.config.ZONES_TO_SYNC or (self.config.SYNC_REVERSE_ZONES and self.is_reverse_zone(zone_name))

    def is_reverse_zone(self, zone_name):
        return zone_name.endswith('.in-addr.arpa') or zone_name.endswith('.ip6.arpa')

    def is_internal_zone(self, zone_name):
        internal_zones = ['0.in-addr.arpa', '127.in-addr.arpa', '255.in-addr.arpa', 'localhost']
        return zone_name in internal_zones or zone_name.endswith('.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.ip6.arpa') # v6 moment

    def sync_zone(self, server_name, zone_name):
        self.logger.info(f"Syncing zone {zone_name} for server {server_name}")
        try:
            remote_records = self.dns_clients[server_name].get_records(zone_name)['records']
            self.logger.debug(f"Fetched {len(remote_records)} remote records for zone {zone_name} on server {server_name}")
            local_records = self.db_manager.get_records(server_name, zone_name)
            self.logger.debug(f"Fetched {len(local_records)} local records for zone {zone_name} on server {server_name}")
            self.process_records(server_name, zone_name, remote_records, local_records)
        except Exception as e:
            self.logger.error(f"Error syncing zone {zone_name} for server {server_name}: {str(e)}", exc_info=True)

    def process_records(self, server_name, zone_name, remote_records, local_records):
        remote_dict = {self.record_key(r, zone_name): r for r in remote_records if r['type'] not in self.excluded_record_types}
        local_dict = {self.record_key(r, zone_name): r for r in local_records if r['type'] not in self.excluded_record_types}

        for key, remote_record in remote_dict.items():
            if key not in local_dict:
                self.logger.debug(f"Adding new record for {server_name} in zone {zone_name}: {remote_record}")
                self.db_manager.add_record(server_name, zone_name, remote_record)
                self.track_change(server_name, zone_name, 'add', remote_record)
            elif not self.records_equal(remote_record, local_dict[key]):
                self.logger.debug(f"Updating record for {server_name} in zone {zone_name}: {remote_record}")
                self.db_manager.update_record(server_name, zone_name, remote_record)
                self.track_change(server_name, zone_name, 'update', remote_record)

        for key in set(local_dict.keys()) - set(remote_dict.keys()):
            self.logger.debug(f"Deleting record for {server_name} in zone {zone_name}: {local_dict[key]}")
            self.db_manager.delete_record(server_name, zone_name, local_dict[key])
            self.track_change(server_name, zone_name, 'delete', local_dict[key])

    def propagate_changes(self):
        self.logger.info("Propagating changes across all servers")
        zones_to_sync = self.db_manager.get_all_zones()
        for zone in zones_to_sync:
            if not self.is_internal_zone(zone):
                zone_owner = self.db_manager.get_zone_owner(zone)
                if zone_owner: # zone owner sync
                    owner_records = self.db_manager.get_records(zone_owner, zone)
                    for server in self.config.SERVERS:
                        if server['name'] != zone_owner:
                            if self.is_reverse_zone(zone):
                                self.ensure_reverse_zone_exists(server['name'], zone)
                            self.update_server_records(server['name'], zone, owner_records, zone_owner)
                else: # catch no own - carry on
                    all_records = self.get_all_records_for_zone(zone)
                    for server in self.config.SERVERS:
                        if self.is_reverse_zone(zone):
                            self.ensure_reverse_zone_exists(server['name'], zone)
                        self.update_server_records(server['name'], zone, all_records, None)

    def update_server_records(self, server_name, zone, target_records, zone_owner):
        self.logger.info(f"Updating records for server {server_name} in zone {zone}")
        try:
            current_records = self.dns_clients[server_name].get_records(zone)['records']
        except Exception as e:
            self.logger.error(f"Failed to get records for server {server_name} in zone {zone}: {str(e)}")
            return

        current_dict = {self.record_key(r, zone): r for r in current_records if r['type'] not in self.excluded_record_types}
        target_dict = {self.record_key(r, zone): r for r in target_records if r['type'] not in self.excluded_record_types}

        for key, record in target_dict.items():
            if key not in current_dict:
                self.logger.debug(f"Adding record to server {server_name}: {record}")
                try:
                    self.dns_clients[server_name].add_record(zone, record['name'], record['type'], record['ttl'], record['rData'])
                    self.track_change(server_name, zone, 'add', record)
                except Exception as e:
                    self.logger.error(f"Error adding record to server {server_name}: {str(e)}")
            elif not self.records_equal(record, current_dict[key]):
                self.logger.debug(f"Updating record on server {server_name}: {record}")
                try:
                    self.dns_clients[server_name].update_record(zone, record['name'], record['type'], current_dict[key]['rData'], record['rData'])
                    self.track_change(server_name, zone, 'update', record)
                except Exception as e:
                    self.logger.error(f"Error updating record on server {server_name}: {str(e)}")

        for key, current_record in current_dict.items():
            if key not in target_dict:
                self.logger.debug(f"Deleting record from server {server_name}: {current_record}")
                try:
                    self.dns_clients[server_name].delete_record(zone, current_record['name'], current_record['type'], current_record['rData'])
                    self.track_change(server_name, zone, 'delete', current_record)
                except Exception as e:
                    self.logger.error(f"Error deleting record from server {server_name}: {str(e)}")

    def get_reverse_zone_from_network(self, network_address, subnet_mask):
        try:
            network = ipaddress.IPv4Network(f"{network_address}/{subnet_mask}", strict=False)
            return f"{network.network_address.reverse_pointer.split('.', 1)[1]}"
        except ValueError:
            self.logger.error(f"Invalid network address or subnet mask: {network_address}/{subnet_mask}")
        return None

    def ensure_reverse_zone_exists(self, server_name, zone):
        try:
            zones = self.dns_clients[server_name].get_zones()
            if zone not in [z['name'] for z in zones.get('zones', [])]:
                self.logger.info(f"Creating reverse zone {zone} on server {server_name}")
                self.dns_clients[server_name].add_zone(zone)
                self.track_change(server_name, zone, 'add', {'type': 'ZONE'})
        except Exception as e:
            self.logger.error(f"Error ensuring reverse zone {zone} exists on server {server_name}: {str(e)}")

    def get_all_records_for_zone(self, zone):
        all_records = {}
        for server in self.config.SERVERS:
            records = self.db_manager.get_records(server['name'], zone)
            for record in records:
                if record['type'] not in self.excluded_record_types:
                    key = self.record_key(record, zone)
                    if key not in all_records:
                        all_records[key] = record
        return list(all_records.values())

    def records_equal(self, record1, record2):
        fields_to_compare = ['name', 'type', 'ttl', 'rData']
        return all(record1.get(field) == record2.get(field) for field in fields_to_compare)

    def track_change(self, server_name, zone_name, change_type, record):
        if zone_name not in self.changes[server_name]:
            self.changes[server_name][zone_name] = {'add': 0, 'update': 0, 'delete': 0}
        self.changes[server_name][zone_name][change_type] += 1

    def log_sync_summary(self):
        self.logger.info("=== Sync Summary ===")
        changes_made = False
        for server_name, server_changes in self.changes.items():
            if server_changes:
                changes_made = True
                self.logger.info(f"Changes for server {server_name}:")
                for zone, changes in server_changes.items():
                    self.logger.info(f"  Zone {zone}:")
                    for change_type, count in changes.items():
                        if count > 0:
                            self.logger.info(f"    {change_type.capitalize()}: {count}")
            else:
                self.logger.info(f"No changes for server {server_name}")
        
        if not changes_made:
            self.logger.info("No changes were made during this sync.")
        
        self.logger.info("=== End of Sync Summary ===")
        self.changes = {server['name']: {} for server in self.config.SERVERS}
        
    @staticmethod
    def record_key(record, zone):
        name = record['name']
        if name.endswith(f".{zone}"):
            name = name[:-len(f".{zone}")]
        elif name == zone:
            name = "@"
        return (name, record['type'], json.dumps(record.get('rData', {}), sort_keys=True))