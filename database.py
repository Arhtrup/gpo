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
            tile_id TEXT,
            crs TEXT,
            width INTEGER,
            height INTEGER,
            min_value REAL,
            max_value REAL,
            mean_value REAL,
            stddev REAL
        )
    ''')
    # Добавляем недостающие колонки для обратной совместимости
    existing_columns = [col[1] for col in c.execute("PRAGMA table_info(images)")]
    for col, col_type in [('crs', 'TEXT'), ('width', 'INTEGER'), ('height', 'INTEGER'),
                          ('min_value', 'REAL'), ('max_value', 'REAL'),
                          ('mean_value', 'REAL'), ('stddev', 'REAL')]:
        if col not in existing_columns:
            c.execute(f"ALTER TABLE images ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()

def add_image(info: SatelliteImageInfo):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO images 
           (filename, date, layer_type, bounds, tile_id, crs, width, height,
            min_value, max_value, mean_value, stddev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (info.filename, info.date.isoformat(), info.layer_type, json.dumps(info.bounds), info.tile_id,
         info.crs, info.width, info.height,
         info.min_value, info.max_value, info.mean_value, info.stddev)
    )
    conn.commit()
    conn.close()

# Остальные функции (get_all_dates, get_layers_for_date, get_image_by_layer_and_date) остаются без изменений
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