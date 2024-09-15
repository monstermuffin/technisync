import requests
import logging
import json

class TechnitiumDNSClient:
    def __init__(self, server_url, api_key):
        self.server_url = server_url
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)

    def _make_request(self, endpoint, params=None, method='GET'):
        url = f"{self.server_url}{endpoint}"
        params = params or {}
        params['token'] = self.api_key
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params)
            elif method == 'POST':
                response = requests.post(url, data=params)
            response.raise_for_status()
            data = response.json()
            
            if data['status'] != 'ok':
                raise Exception(f"API error: {data.get('errorMessage', 'Unknown error')}")
            
            return data.get('response', {})
        except requests.RequestException as e:
            self.logger.error(f"Error making request to {url}: {e}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON response from {url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in request to {url}: {e}")
            raise

    def get_zones(self):
        return self._make_request('/api/zones/list')

    def get_records(self, domain):
        return self._make_request('/api/zones/records/get', {'domain': domain, 'listZone': 'true'})

    def add_record(self, zone, name, record_type, ttl, data):
        params = {
            'domain': name if name != '@' else zone,
            'zone': zone,
            'type': record_type,
            'ttl': ttl,
        }
        params.update(self._format_rdata(record_type, data))
        return self._make_request('/api/zones/records/add', params, method='POST')

    def update_record(self, zone, name, record_type, old_data, new_data):
        params = {
            'domain': name if name != '@' else zone,
            'zone': zone,
            'type': record_type,
        }
        params.update(self._format_rdata(record_type, old_data, prefix=''))
        params.update(self._format_rdata(record_type, new_data, prefix='new'))
        return self._make_request('/api/zones/records/update', params, method='POST')

    def delete_record(self, zone, name, record_type, data):
        params = {
            'domain': name if name != '@' else zone,
            'zone': zone,
            'type': record_type,
        }
        params.update(self._format_rdata(record_type, data))
        return self._make_request('/api/zones/records/delete', params, method='POST')

    def add_zone(self, zone_name):
        params = {
            'domain': zone_name,
            'type': 'Primary'
        }
        return self._make_request('/api/zones/create', params, method='POST')

    @staticmethod
    def _format_rdata(record_type, data, prefix=''):
        formatted = {}
        if record_type == 'A' or record_type == 'AAAA':
            formatted[f'{prefix}ipAddress'] = data['ipAddress']
        elif record_type == 'CNAME':
            formatted[f'{prefix}cname'] = data['cname']
        elif record_type == 'MX':
            formatted[f'{prefix}preference'] = data['preference']
            formatted[f'{prefix}exchange'] = data['exchange']
        elif record_type == 'NS':
            formatted[f'{prefix}nameServer'] = data['nameServer']
        elif record_type == 'TXT':
            formatted[f'{prefix}text'] = data['text']
        elif record_type == 'SOA':
            formatted[f'{prefix}primaryNameServer'] = data['primaryNameServer']
            formatted[f'{prefix}responsiblePerson'] = data['responsiblePerson']
            formatted[f'{prefix}serial'] = data['serial']
            formatted[f'{prefix}refresh'] = data['refresh']
            formatted[f'{prefix}retry'] = data['retry']
            formatted[f'{prefix}expire'] = data['expire']
            formatted[f'{prefix}minimum'] = data['minimum']
        elif record_type == 'PTR':
            formatted[f'{prefix}ptrName'] = data['ptrName']
        return formatted

    def get_dhcp_scopes(self):
        return self._make_request('/api/dhcp/scopes/list')

    def get_dhcp_scope(self, scope_name):
        return self._make_request('/api/dhcp/scopes/get', {'name': scope_name})