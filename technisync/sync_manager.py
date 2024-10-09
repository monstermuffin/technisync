import logging
import json
from datetime import datetime, timezone
import ipaddress
from .models import DNSRecord, Server, ZoneOwnership, is_reverse_zone, is_internal_zone, get_reverse_zone_from_network

class SyncManager:
    def __init__(self, config, db_manager, dns_clients):
        self.config = config
        self.db_manager = db_manager
        self.dns_clients = dns_clients
        self.logger = logging.getLogger(__name__)
        self.changes = {server.name: {} for server in config.SERVERS}
        self.excluded_record_types = [
            'SOA', 'NS', 'RRSIG', 'NSEC', 'NSEC3', 'DNSKEY', 'DS',
            'CDS', 'CDNSKEY', 'TSIG', 'TKEY', 'AXFR', 'IXFR'
        ]

    def sync(self):
        for server in self.config.SERVERS:
            self.logger.info(f"Syncing records for server: {server.name}")
            try:
                zones = self.dns_clients[server.name].get_zones()
                self.logger.debug(f"Fetched zones for server {server.name}: {zones}")
                for zone in zones.get('zones', []):
                    if self.should_sync_zone(zone['name']):
                        self.sync_zone(server.name, zone['name'])
                
                if self.config.SYNC_REVERSE_ZONES:
                    self.sync_dhcp_scopes(server.name)
            except Exception as e:
                self.logger.error(f"Error syncing server {server.name}: {str(e)}", exc_info=True)

        self.propagate_changes()
        self.log_sync_summary()

    def should_sync_zone(self, zone_name):
        if is_internal_zone(zone_name):
            return False
        if not self.config.ZONES_TO_SYNC:
            return True 
        return zone_name in self.config.ZONES_TO_SYNC or (self.config.SYNC_REVERSE_ZONES and is_reverse_zone(zone_name))

    def sync_zone(self, server_name, zone_name):
        self.logger.info(f"Syncing zone {zone_name} for server {server_name}")
        try:
            remote_records = self.dns_clients[server_name].get_records(zone_name)['records']
            self.logger.debug(f"Fetched {len(remote_records)} remote records for zone {zone_name} on server {server_name}")
            local_records = self.db_manager.get_records(server_name, zone_name)
            deleted_records = self.db_manager.get_deleted_records(server_name, zone_name)
            self.logger.debug(f"Fetched {len(local_records)} local records and {len(deleted_records)} deleted records for zone {zone_name} on server {server_name}")
            self.process_records(server_name, zone_name, remote_records, local_records, deleted_records)
        except Exception as e:
            self.logger.error(f"Error syncing zone {zone_name} for server {server_name}: {str(e)}", exc_info=True)

    def is_valid_record_for_server(self, server_name, record):
        if record.type in ('A', 'AAAA'):
            reverse_zone_owner = self.get_reverse_zone_owner(record.rdata['ipAddress'])
            return reverse_zone_owner is None or reverse_zone_owner == server_name or self.is_replicated_record(server_name, record)
        return True

    def is_replicated_record(self, server_name, record):
        for other_server in self.config.SERVERS:
            if other_server.name != server_name:
                other_server_records = self.db_manager.get_records(other_server.name, record.name.split('.', 1)[1])
                if any(r for r in other_server_records if r == record):
                    return True
        return False

    def process_records(self, server_name, zone_name, remote_records, local_records, deleted_records):
        remote_dict = {self.record_key(DNSRecord.from_dict(r)): DNSRecord.from_dict(r) 
                    for r in remote_records if r['type'] not in self.excluded_record_types}
        local_dict = {self.record_key(r): r for r in local_records if r.type not in self.excluded_record_types}
        deleted_dict = {self.record_key(r): r for r in deleted_records}

        for key, remote_record in remote_dict.items():
            if not self.is_valid_record_for_server(server_name, remote_record):
                self.logger.warning(f"Invalid {remote_record.type} record found on {server_name} in zone {zone_name}: {remote_record}")
                self.db_manager.mark_record_as_deleted(server_name, zone_name, remote_record)
                self.track_change(server_name, zone_name, 'delete', remote_record)
                
                if remote_record.type in ('A', 'AAAA'):
                    ptr_zone = self.ip_to_reverse_zone(remote_record.rdata['ipAddress'])
                    if ptr_zone:
                        ptr_name = ipaddress.ip_address(remote_record.rdata['ipAddress']).reverse_pointer
                        ptr_record = DNSRecord(name=ptr_name, record_type='PTR', ttl=remote_record.ttl, rdata={'ptrName': remote_record.name})
                        self.db_manager.mark_record_as_deleted(server_name, ptr_zone, ptr_record)
                        self.track_change(server_name, ptr_zone, 'delete', ptr_record)
                
                continue

            if key in deleted_dict:
                self.logger.debug(f"Deleting previously deleted record on {server_name} in zone {zone_name}: {remote_record}")
                self.dns_clients[server_name].delete_record(zone_name, remote_record.name, remote_record.type, remote_record.rdata)
                self.track_change(server_name, zone_name, 'delete', remote_record)
            elif key not in local_dict:
                self.logger.debug(f"Adding record for {server_name} in zone {zone_name}: {remote_record}")
                self.db_manager.add_or_update_record(server_name, zone_name, remote_record)
                self.track_change(server_name, zone_name, 'add', remote_record)
            elif remote_record != local_dict[key]:
                self.logger.debug(f"Updating record for {server_name} in zone {zone_name}: {remote_record}")
                self.db_manager.add_or_update_record(server_name, zone_name, remote_record)
                self.track_change(server_name, zone_name, 'update', remote_record)

        for key, local_record in local_dict.items():
            if key not in remote_dict and key not in deleted_dict:
                self.logger.debug(f"Marking record as deleted for {server_name} in zone {zone_name}: {local_record}")
                self.db_manager.mark_record_as_deleted(server_name, zone_name, local_record)
                self.track_change(server_name, zone_name, 'delete', local_record)

    def propagate_changes(self):
        self.logger.info("Propagating changes across all servers")
        zones_to_sync = self.db_manager.get_all_zones()
        for zone in zones_to_sync:
            if not is_internal_zone(zone):
                zone_owner = self.db_manager.get_zone_owner(zone)
                if zone_owner:
                    owner_records = self.db_manager.get_records(zone_owner, zone)
                    for server in self.config.SERVERS:
                        if server.name != zone_owner:
                            if is_reverse_zone(zone):
                                self.ensure_reverse_zone_exists(server.name, zone)
                            self.update_server_records(server.name, zone, owner_records, zone_owner)
                else:
                    all_records = self.get_all_records_for_zone(zone)
                    for server in self.config.SERVERS:
                        if is_reverse_zone(zone):
                            self.ensure_reverse_zone_exists(server.name, zone)
                        self.update_server_records(server.name, zone, all_records, None)

    def update_server_records(self, server_name, zone, target_records, zone_owner):
        self.logger.info(f"Updating records for server {server_name} in zone {zone}")
        try:
            current_records = self.dns_clients[server_name].get_records(zone)['records']
            deleted_records = self.db_manager.get_deleted_records(server_name, zone)
        except Exception as e:
            self.logger.error(f"Failed to get records for server {server_name} in zone {zone}: {str(e)}")
            return

        current_dict = {self.record_key(DNSRecord.from_dict(r)): DNSRecord.from_dict(r) 
                        for r in current_records if r['type'] not in self.excluded_record_types}
        target_dict = {self.record_key(r): r for r in target_records if r.type not in self.excluded_record_types}
        deleted_dict = {self.record_key(r): r for r in deleted_records}

        for key, current_record in current_dict.items():
            if key not in target_dict or key in deleted_dict:
                self.logger.debug(f"Deleting record from server {server_name}: {current_record}")
                try:
                    self.dns_clients[server_name].delete_record(zone, current_record.name, current_record.type, current_record.rdata)
                    self.track_change(server_name, zone, 'delete', current_record)
                except Exception as e:
                    self.logger.error(f"Error deleting record from server {server_name}: {str(e)}")

        for key, record in target_dict.items():
            if key in deleted_dict:
                continue
            if record.type in ('A', 'AAAA'):
                reverse_zone_owner = self.get_reverse_zone_owner(record.rdata['ipAddress'])
                if reverse_zone_owner and reverse_zone_owner != server_name:
                    if key not in current_dict:
                        self.logger.debug(f"Adding A/AAAA record to server {server_name}: {record}")
                        try:
                            self.dns_clients[server_name].add_record(zone, record.name, record.type, record.ttl, record.rdata)
                            self.track_change(server_name, zone, 'add', record)
                        except Exception as e:
                            self.logger.error(f"Error adding A/AAAA record to server {server_name}: {str(e)}")
                    elif record != current_dict[key]:
                        self.logger.debug(f"Updating A/AAAA record on server {server_name}: {record}")
                        try:
                            self.dns_clients[server_name].update_record(zone, record.name, record.type, current_dict[key].rdata, record.rdata)
                            self.track_change(server_name, zone, 'update', record)
                        except Exception as e:
                            self.logger.error(f"Error updating A/AAAA record on server {server_name}: {str(e)}")
                    continue
            if key not in current_dict:
                self.logger.debug(f"Adding record to server {server_name}: {record}")
                try:
                    self.dns_clients[server_name].add_record(zone, record.name, record.type, record.ttl, record.rdata)
                    self.track_change(server_name, zone, 'add', record)
                except Exception as e:
                    self.logger.error(f"Error adding record to server {server_name}: {str(e)}")
            elif record != current_dict[key]:
                self.logger.debug(f"Updating record on server {server_name}: {record}")
                try:
                    self.dns_clients[server_name].update_record(zone, record.name, record.type, current_dict[key].rdata, record.rdata)
                    self.track_change(server_name, zone, 'update', record)
                except Exception as e:
                    self.logger.error(f"Error updating record on server {server_name}: {str(e)}")

    def sync_dhcp_scopes(self, server_name):
        try:
            dhcp_scopes = self.dns_clients[server_name].get_dhcp_scopes()
            for scope in dhcp_scopes.get('scopes', []):
                reverse_zone = get_reverse_zone_from_network(scope['networkAddress'], scope['subnetMask'])
                if reverse_zone:
                    for srv in self.config.SERVERS:
                        self.ensure_reverse_zone_exists(srv.name, reverse_zone)
                    self.db_manager.set_zone_owner(reverse_zone, server_name)
                    self.sync_zone(server_name, reverse_zone)
        except Exception as e:
            self.logger.error(f"Error syncing DHCP scopes for server {server_name}: {str(e)}", exc_info=True)

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
            records = self.db_manager.get_records(server.name, zone)
            for record in records:
                if record.type not in self.excluded_record_types:
                    key = self.record_key(record)
                    if key not in all_records:
                        all_records[key] = record
        return list(all_records.values())

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
            self.changes = {server.name: {} for server in self.config.SERVERS}

    def record_key(self, record):
        return (record.name, record.type, json.dumps(record.rdata, sort_keys=True))

    def get_reverse_zone_owner(self, ip_address):
        reverse_zone = self.ip_to_reverse_zone(ip_address)
        if reverse_zone:
            return self.db_manager.get_zone_owner(reverse_zone)
        return None

    @staticmethod
    def ip_to_reverse_zone(ip_address):
        try:
            ip = ipaddress.ip_address(ip_address)
            if isinstance(ip, ipaddress.IPv4Address):
                return f"{ip.reverse_pointer.split('.', 1)[1]}"
            elif isinstance(ip, ipaddress.IPv6Address):
                return f"{ip.reverse_pointer.split('.', 16)[16]}"
        except ValueError:
            return None