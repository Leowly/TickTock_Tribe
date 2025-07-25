import os
import sqlite3
from contextlib import closing

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # core目录
DATA_DIR = os.path.join(BASE_DIR, '..', 'database')
os.makedirs(DATA_DIR, exist_ok=True)  # 确保目录存在

DB_PATH = os.path.join(DATA_DIR, 'world_maps.db')

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS world_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                map_data BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

def insert_map(name: str, width: int, height: int, map_bytes: bytes):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            cursor = conn.execute(
                "INSERT INTO world_maps (name, width, height, map_data) VALUES (?, ?, ?, ?)",
                (name, width, height, map_bytes)
            )
            return cursor.lastrowid

def get_map_by_id(map_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT width, height, map_data FROM world_maps WHERE id=?", (map_id,))
        return cursor.fetchone()

def get_maps_list():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT id, name, width, height, created_at FROM world_maps ORDER BY created_at DESC")
        return cursor.fetchall()
