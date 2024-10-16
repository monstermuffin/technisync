import sqlite3
import json
from datetime import datetime, timezone
from .models import DNSRecord, ZoneOwnership

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.connect()
        self.check_and_create_tables()

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def check_and_create_tables(self):
        self.check_and_create_dns_records_table()
        self.check_and_create_zone_ownership_table()
        self.check_and_create_zone_sync_table()

    def check_and_create_dns_records_table(self):
        self.cursor.execute("PRAGMA table_info(dns_records)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        required_columns = ['id', 'server', 'zone', 'name', 'type', 'ttl', 'rdata', 'created_at', 'updated_at', 'last_operation']
        
        if set(required_columns).issubset(set(columns)):
            return  

        self.cursor.execute("DROP TABLE IF EXISTS dns_records")
        self.create_dns_records_table()

    def create_dns_records_table(self):
        self.cursor.execute('''
            CREATE TABLE dns_records (
                id INTEGER PRIMARY KEY,
                server TEXT,
                zone TEXT,
                name TEXT,
                type TEXT,
                ttl INTEGER,
                rdata TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                last_operation TEXT
            )
        ''')
        self.conn.commit()

    def check_and_create_zone_ownership_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS zone_ownership (
                id INTEGER PRIMARY KEY,
                zone TEXT UNIQUE,
                owner TEXT,
                created_at TIMESTAMP
            )
        ''')
        self.conn.commit()

    def get_records(self, server_name, zone_name):
        self.cursor.execute('''
            SELECT name, type, ttl, rdata, last_operation
            FROM dns_records
            WHERE server = ? AND zone = ? AND last_operation != 'DELETE'
        ''', (server_name, zone_name))
        records = self.cursor.fetchall()
        return [
            DNSRecord(
                name=record[0],
                record_type=record[1],
                ttl=record[2],
                rdata=json.loads(record[3])
            )
            for record in records
        ]

    def add_or_update_record(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            INSERT OR REPLACE INTO dns_records 
            (server, zone, name, type, ttl, rdata, created_at, updated_at, last_operation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ADD')
        ''', (
            server_name,
            zone_name,
            record.name,
            record.type,
            record.ttl,
            json.dumps(record.rdata),
            now,
            now
        ))
        self.conn.commit()

    def delete_record(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            UPDATE dns_records
            SET updated_at = ?, last_operation = 'DELETE'
            WHERE server = ? AND zone = ? AND name = ? AND type = ?
        ''', (
            now,
            server_name,
            zone_name,
            record.name,
            record.type
        ))
        self.conn.commit()

    def get_deleted_records(self, server_name, zone_name):
        self.cursor.execute('''
            SELECT name, type, ttl, rdata
            FROM dns_records
            WHERE server = ? AND zone = ? AND last_operation = 'DELETE'
        ''', (server_name, zone_name))
        records = self.cursor.fetchall()
        return [
            DNSRecord(
                name=record[0],
                record_type=record[1],
                ttl=record[2],
                rdata=json.loads(record[3])
            )
            for record in records
        ]

    def get_zone_owner(self, zone):
        self.cursor.execute('SELECT owner FROM zone_ownership WHERE zone = ?', (zone,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def set_zone_owner(self, zone, owner):
        zone_ownership = ZoneOwnership(zone, owner)
        self.cursor.execute('''
            INSERT OR REPLACE INTO zone_ownership (zone, owner, created_at)
            VALUES (?, ?, ?)
        ''', (zone_ownership.zone, zone_ownership.owner, zone_ownership.created_at))
        self.conn.commit()

    def get_all_zones(self):
        self.cursor.execute('SELECT DISTINCT zone FROM dns_records')
        return [row[0] for row in self.cursor.fetchall()]

    def mark_record_as_deleted(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            INSERT OR REPLACE INTO dns_records
            (server, zone, name, type, ttl, rdata, created_at, updated_at, last_operation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'DELETE')
        ''', (
            server_name,
            zone_name,
            record.name,
            record.type,
            record.ttl,
            json.dumps(record.rdata),
            now,
            now
        ))
        self.conn.commit()

    def check_and_create_zone_sync_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS zone_sync (
                id INTEGER PRIMARY KEY,
                zone TEXT,
                server TEXT,
                last_synced TIMESTAMP,
                UNIQUE(zone, server)
            )
        ''')
        self.conn.commit()

    def update_zone_sync(self, zone, server):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            INSERT OR REPLACE INTO zone_sync (zone, server, last_synced)
            VALUES (?, ?, ?)
        ''', (zone, server, now))
        self.conn.commit()

    def get_zone_sync(self, zone, server):
        self.cursor.execute('''
            SELECT last_synced FROM zone_sync
            WHERE zone = ? AND server = ?
        ''', (zone, server))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()