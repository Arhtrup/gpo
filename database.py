import sqlite3
import json
from settings import DATABASE_PATH
from models import SatelliteImageInfo

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS images (
            filename TEXT PRIMARY KEY,
            date TEXT,
            layer_type TEXT,
            bounds TEXT,
            tile_id TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_image(info: SatelliteImageInfo):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO images (filename, date, layer_type, bounds, tile_id) VALUES (?, ?, ?, ?, ?)",
        (info.filename, info.date.isoformat(), info.layer_type, json.dumps(info.bounds), info.tile_id)
    )
    conn.commit()
    conn.close()

def get_all_dates():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM images ORDER BY date DESC")
    result = [row[0] for row in c.fetchall()]
    conn.close()
    return result

def get_layers_for_date(date_str: str):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT layer_type, filename, bounds FROM images WHERE date = ?", (date_str,))
    result = [{"layer": row[0], "filename": row[1], "bounds": json.loads(row[2])} for row in c.fetchall()]
    conn.close()
    return result

def get_image_by_layer_and_date(date_str: str, layer: str):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, bounds FROM images WHERE date = ? AND layer_type = ?", (date_str, layer))
    row = c.fetchone()
    conn.close()
    if row:
        return {"filename": row[0], "bounds": json.loads(row[1])}
    return None