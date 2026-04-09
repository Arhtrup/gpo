import sqlite3
import json
from settings import DATABASE_PATH
from models import SatelliteImageInfo
from logger import app_logger

def init_db():
    try:
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
                stddev REAL,
                bounds_wgs84 TEXT
            )
        ''')
        existing_columns = [col[1] for col in c.execute("PRAGMA table_info(images)")]
        added = 0
        for col, col_type in [('crs', 'TEXT'), ('width', 'INTEGER'), ('height', 'INTEGER'),
                              ('min_value', 'REAL'), ('max_value', 'REAL'),
                              ('mean_value', 'REAL'), ('stddev', 'REAL'),
                              ('bounds_wgs84', 'TEXT')]:
            if col not in existing_columns:
                c.execute(f"ALTER TABLE images ADD COLUMN {col} {col_type}")
                added += 1
        conn.commit()
        app_logger.info(f"База данных инициализирована: {DATABASE_PATH} (добавлено колонок: {added})")
    except Exception as e:
        app_logger.error(f"Ошибка инициализации БД: {e}", exc_info=True)
        raise
    finally:
        conn.close()

def add_image(info: SatelliteImageInfo):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO images 
               (filename, date, layer_type, bounds, tile_id, crs, width, height,
                min_value, max_value, mean_value, stddev, bounds_wgs84)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (info.filename, info.date.isoformat(), info.layer_type, json.dumps(info.bounds), info.tile_id,
             info.crs, info.width, info.height,
             info.min_value, info.max_value, info.mean_value, info.stddev,
             json.dumps(info.bounds_wgs84) if info.bounds_wgs84 else None)
        )
        conn.commit()
        app_logger.debug(f"Добавлена/обновлена запись: {info.filename}")
    except Exception as e:
        app_logger.error(f"Ошибка добавления изображения {info.filename}: {e}", exc_info=True)
    finally:
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
    c.execute("SELECT layer_type, filename, bounds_wgs84 FROM images WHERE date = ?", (date_str,))
    result = [{"layer": row[0], "filename": row[1], "bounds": json.loads(row[2])} for row in c.fetchall() if row[2] is not None]
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

# НОВАЯ ФУНКЦИЯ: получение статистики из БД
def get_statistics_for_layer(date: str, layer: str):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT min_value, max_value, mean_value, stddev 
        FROM images WHERE date = ? AND layer_type = ?
    """, (date, layer))
    row = c.fetchone()
    conn.close()
    if row and row[0] is not None:
        return {
            "min": row[0],
            "max": row[1],
            "mean": row[2],
            "stddev": row[3],
            "valid_percent": None   # можно расширить при необходимости
        }
    return None