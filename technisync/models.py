import json
from datetime import datetime, timezone
import ipaddress

class DNSRecord:
    def __init__(self, name, record_type, ttl, rdata):
        self.name = name
        self.type = record_type
        self.ttl = ttl
        self.rdata = rdata

    def __eq__(self, other):
        if not isinstance(other, DNSRecord):
            return False
        return (self.name == other.name and
                self.type == other.type and
                self.ttl == other.ttl and
                self.rdata == other.rdata)

    def __hash__(self):
        return hash((self.name, self.type, self.ttl, frozenset(self.rdata.items())))

    def to_dict(self):
        return {
            'name': self.name,
            'type': self.type,
            'ttl': self.ttl,
            'rData': self.rdata
        }

    @classmethod
    def from_dict(cls, record_dict):
        return cls(
            name=record_dict['name'],
            record_type=record_dict['type'],
            ttl=record_dict['ttl'],
            rdata=record_dict['rData']
        )

    def __repr__(self):
        return f"DNSRecord(name='{self.name}', type='{self.type}', ttl={self.ttl}, rdata={self.rdata})"

class Server:
    def __init__(self, name, url, api_key):
        self.name = name
        self.url = url
        self.api_key = api_key

    def __repr__(self):
        return f"Server(name='{self.name}', url='{self.url}')"

class ZoneSync:
    def __init__(self, zone, server, last_synced):
        self.zone = zone
        self.server = server
        self.last_synced = last_synced
        
class ZoneOwnership:
    def __init__(self, zone, owner, created_at=None):
        self.zone = zone
        self.owner = owner
        self.created_at = created_at or datetime.now(timezone.utc)

    def __repr__(self):
        return f"ZoneOwnership(zone='{self.zone}', owner='{self.owner}', created_at={self.created_at})"

def is_reverse_zone(zone_name):
    return zone_name.endswith('.in-addr.arpa') or zone_name.endswith('.ip6.arpa')

def is_internal_zone(zone_name):
    internal_zones = ['0.in-addr.arpa', '127.in-addr.arpa', '255.in-addr.arpa', 'localhost']
    return zone_name in internal_zones or zone_name.endswith('.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.ip6.arpa')

def get_reverse_zone_from_network(network_address, subnet_mask):
    try:
        network = ipaddress.IPv4Network(f"{network_address}/{subnet_mask}", strict=False)
        return f"{network.network_address.reverse_pointer.split('.', 1)[1]}"
    except ValueError:
        return None