# fix_bounds.py
import sqlite3
import json
import rasterio
from rasterio.warp import transform_bounds
import os
from settings import IMAGES_DIR, DATABASE_PATH
from logger import app_logger

def fix_all_bounds():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    # Получаем все записи, у которых bounds_wgs84 или crs могут быть неверными
    c.execute("SELECT filename, bounds, crs FROM images")
    rows = c.fetchall()
    updated = 0
    for filename, bounds_json, crs_str in rows:
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            app_logger.warning(f"Файл не найден: {filepath}")
            continue
        
        # Пытаемся открыть файл и получить реальный CRS
        try:
            with rasterio.open(filepath) as src:
                if src.crs:
                    crs = src.crs.to_string()
                else:
                    # Если CRS нет в файле, пробуем определить по имени (для Sentinel-2)
                    if 'T45VUC' in filename:
                        crs = "EPSG:32645"  # UTM зона 45N
                        app_logger.info(f"Принудительно задан CRS EPSG:32645 для {filename}")
                    else:
                        app_logger.warning(f"Не удалось определить CRS для {filename}, пропускаем")
                        continue
                
                bounds = src.bounds  # (left, bottom, right, top)
                # Преобразуем в WGS84
                bounds_wgs84 = transform_bounds(crs, 'EPSG:4326', *bounds)
                # Обновляем запись в БД
                c.execute("""
                    UPDATE images 
                    SET crs = ?, bounds_wgs84 = ?
                    WHERE filename = ?
                """, (crs, json.dumps(bounds_wgs84), filename))
                updated += 1
                app_logger.info(f"Обновлено: {filename} -> {bounds_wgs84}")
        except Exception as e:
            app_logger.error(f"Ошибка обработки {filename}: {e}")
    
    conn.commit()
    conn.close()
    print(f"Обновлено записей: {updated}")

if __name__ == "__main__":
    fix_all_bounds()