import sqlite3
import json
from datetime import datetime, timezone

class DatabaseManager: # fixed chatgpt database nonsense
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.check_and_create_tables()

    def check_and_create_tables(self):
        self.check_and_create_dns_records_table()
        self.check_and_create_zone_ownership_table()

    def check_and_create_dns_records_table(self):
        self.cursor.execute("PRAGMA table_info(dns_records)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        required_columns = ['id', 'server', 'zone', 'name', 'type', 'ttl', 'rdata', 'created_at', 'updated_at', 'deleted_at']
        
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
                deleted_at TIMESTAMP
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
            SELECT name, type, ttl, rdata
            FROM dns_records
            WHERE server = ? AND zone = ? AND deleted_at IS NULL
        ''', (server_name, zone_name))
        records = self.cursor.fetchall()
        return [
            {
                'name': record[0],
                'type': record[1],
                'ttl': record[2],
                'rData': json.loads(record[3])
            }
            for record in records
        ]

    def add_record(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            INSERT OR REPLACE INTO dns_records 
            (server, zone, name, type, ttl, rdata, created_at, updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ''', (
            server_name,
            zone_name,
            record['name'],
            record['type'],
            record['ttl'],
            json.dumps(record['rData']),
            now,
            now
        ))
        self.conn.commit()

    def update_record(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            UPDATE dns_records
            SET ttl = ?, rdata = ?, updated_at = ?
            WHERE server = ? AND zone = ? AND name = ? AND type = ? AND deleted_at IS NULL
        ''', (
            record['ttl'],
            json.dumps(record['rData']),
            now,
            server_name,
            zone_name,
            record['name'],
            record['type']
        ))
        self.conn.commit()

    def delete_record(self, server_name, zone_name, record):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            UPDATE dns_records
            SET deleted_at = ?
            WHERE server = ? AND zone = ? AND name = ? AND type = ? AND deleted_at IS NULL
        ''', (
            now,
            server_name,
            zone_name,
            record['name'],
            record['type']
        ))
        self.conn.commit()

    def get_zone_owner(self, zone):
        self.cursor.execute('SELECT owner FROM zone_ownership WHERE zone = ?', (zone,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def set_zone_owner(self, zone, owner):
        now = datetime.now(timezone.utc)
        self.cursor.execute('''
            INSERT OR REPLACE INTO zone_ownership (zone, owner, created_at)
            VALUES (?, ?, ?)
        ''', (zone, owner, now))
        self.conn.commit()

    def get_all_zones(self):
        self.cursor.execute('SELECT DISTINCT zone FROM dns_records')
        return [row[0] for row in self.cursor.fetchall()]

    def __del__(self):
        self.conn.close()