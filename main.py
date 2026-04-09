from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import sqlite3
from datetime import datetime
import json
import rasterio
from rasterio.warp import transform_bounds
import io
from PIL import Image
import database
import tile_utils
from geotiff_parser import parse_geotiff_metadata
from logger import app_logger
from settings import (
    IMAGES_DIR, PRODUCT_SUBDIRS, DB_INIT_TABLE, WEB_TITLE,
    COLOR_BACKGROUND, COLOR_CONTROLS_BG, COLOR_BUTTON, COLOR_BUTTON_HOVER,
    COLOR_SELECT_BG, COLOR_SELECT_HOVER, COLOR_TEXT_LIGHT,
    MAP_HEIGHT, MAP_HEIGHT_MOBILE, CONTROLS_PADDING,
    DEFAULT_OPACITY, DEFAULT_MAP_ZOOM, DEFAULT_MAP_CENTER, MAX_ZOOM_TILES,
    HOST, PORT, ENABLE_COMPARE,
    DEFAULT_BASE_TILE_URL, DEFAULT_BASE_ATTRIBUTION, DEFAULT_BASE_MAX_ZOOM,
    TEMPLATES_DIR, CORS_ALLOW_ORIGINS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS
)
from models import SatelliteImageInfo

app_logger.info("Запуск спутникового просмотрщика")

if DB_INIT_TABLE:
    database.init_db()
    app_logger.debug("База данных проинициализирована")

# ========== МИГРАЦИИ ==========
def migrate_existing_records():
    conn = sqlite3.connect(database.DATABASE_PATH)
    c = conn.cursor()
    # Добавляем колонку bounds_wgs84, если её нет
    c.execute("PRAGMA table_info(images)")
    cols = [row[1] for row in c.fetchall()]
    if 'bounds_wgs84' not in cols:
        c.execute("ALTER TABLE images ADD COLUMN bounds_wgs84 TEXT")
        conn.commit()
        app_logger.info("Добавлена колонка bounds_wgs84")

    c.execute("SELECT filename, bounds, crs FROM images WHERE bounds_wgs84 IS NULL")
    rows = c.fetchall()
    app_logger.info(f"Найдено {len(rows)} записей для миграции bounds_wgs84")
    for filename, bounds_json, crs_str in rows:
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            app_logger.warning(f"Файл не найден: {filepath}")
            continue
        try:
            with rasterio.open(filepath) as src:
                bounds = json.loads(bounds_json)
                if src.crs:
                    bounds_wgs84 = transform_bounds(src.crs, 'EPSG:4326', *bounds)
                else:
                    # Если CRS нет в файле, пробуем определить по имени (для Sentinel-2)
                    if 'T45VUC' in filename:
                        crs = "EPSG:32645"
                        bounds_wgs84 = transform_bounds(crs, 'EPSG:4326', *bounds)
                    else:
                        app_logger.warning(f"Невозможно определить CRS для {filename}, bounds_wgs84 не обновлён")
                        continue
                c.execute("UPDATE images SET bounds_wgs84 = ?, crs = ? WHERE filename = ?",
                          (json.dumps(bounds_wgs84), src.crs.to_string() if src.crs else crs, filename))
                app_logger.debug(f"Миграция {filename}: {bounds_wgs84}")
        except Exception as e:
            app_logger.error(f"Ошибка миграции {filename}: {e}")
    conn.commit()
    conn.close()
    app_logger.info("Миграция bounds_wgs84 завершена")

def migrate_metadata():
    conn = sqlite3.connect(database.DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT filename FROM images WHERE crs IS NULL OR width IS NULL")
    rows = c.fetchall()
    app_logger.info(f"Найдено {len(rows)} записей для миграции метаданных")
    for (filename,) in rows:
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            continue
        try:
            meta = parse_geotiff_metadata(filepath)
            c.execute("""
                UPDATE images 
                SET crs = ?, width = ?, height = ?, 
                    min_value = ?, max_value = ?, mean_value = ?, stddev = ?,
                    bounds_wgs84 = ?
                WHERE filename = ?
            """, (meta['crs'], meta['width'], meta['height'],
                  meta['min_value'], meta['max_value'], meta['mean_value'], meta['stddev'],
                  json.dumps(meta['bounds_wgs84']), filename))
        except Exception as e:
            app_logger.error(f"Ошибка миграции {filename}: {e}")
    conn.commit()
    conn.close()

if database.get_all_dates():
    app_logger.info("Обнаружены существующие записи, запускаем миграции")
    migrate_existing_records()
    migrate_metadata()
else:
    app_logger.info("База данных пуста, будет выполнено сканирование файлов")

# ========== СКАНИРОВАНИЕ ФАЙЛОВ (без изменений) ==========
def parse_filename(filename):
    base = os.path.splitext(filename)[0]
    parts = base.split('_')
    if len(parts) >= 3:
        tile_id = parts[0]
        datetime_str = parts[1]
        try:
            dt = datetime.strptime(datetime_str.split('T')[0], "%Y%m%d").date()
            return tile_id, dt
        except Exception:
            return None
    return None

if not database.get_all_dates():
    app_logger.info("Начинаем сканирование папок с TIFF-файлами")
    for product_type in PRODUCT_SUBDIRS:
        product_dir = os.path.join(IMAGES_DIR, product_type)
        if not os.path.isdir(product_dir):
            app_logger.warning(f"Папка не найдена: {product_dir}")
            continue
        app_logger.info(f"Сканируем {product_dir}")
        for fname in os.listdir(product_dir):
            if not fname.lower().endswith(('.tiff', '.tif')):
                continue
            parsed = parse_filename(fname)
            if parsed is None:
                app_logger.warning(f"Пропускаем {fname}: не удалось распарсить имя")
                continue
            tile_id, dt = parsed
            filepath = os.path.join(product_dir, fname)
            try:
                meta = parse_geotiff_metadata(filepath)
            except Exception as e:
                app_logger.error(f"Ошибка чтения метаданных {filepath}: {e}")
                # fallback: минимальные данные
                try:
                    with rasterio.open(filepath) as src:
                        bounds = src.bounds
                        crs = src.crs.to_string() if src.crs else None
                        width, height = src.width, src.height
                        bounds_wgs84 = transform_bounds(src.crs, 'EPSG:4326', *bounds) if src.crs else bounds
                    meta = {
                        'bounds': bounds,
                        'bounds_wgs84': bounds_wgs84,
                        'crs': crs,
                        'width': width,
                        'height': height,
                        'min_value': None,
                        'max_value': None,
                        'mean_value': None,
                        'stddev': None
                    }
                except Exception as e2:
                    app_logger.error(f"Не удалось открыть {filepath}: {e2}")
                    continue

            rel_path = os.path.join(product_type, fname)
            info = SatelliteImageInfo(
                filename=rel_path,
                date=dt,
                layer_type=product_type,
                bounds=meta['bounds'],
                bounds_wgs84=meta['bounds_wgs84'],
                tile_id=tile_id,
                crs=meta['crs'],
                width=meta['width'],
                height=meta['height'],
                min_value=meta['min_value'],
                max_value=meta['max_value'],
                mean_value=meta['mean_value'],
                stddev=meta['stddev']
            )
            database.add_image(info)
            app_logger.info(f"Добавлено в БД: {rel_path} (bounds_wgs84={meta['bounds_wgs84']})")
    app_logger.info("Сканирование завершено")

# ========== FASTAPI APP ==========
app = FastAPI(title=WEB_TITLE)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

@app.get("/api/dates", response_model=list[str])
async def get_dates():
    dates = database.get_all_dates()
    return dates

@app.get("/api/layers/{date}")
async def get_layers(date: str):
    layers = database.get_layers_for_date(date)
    app_logger.debug(f"Слои для {date}: {layers}")
    return layers

@app.get("/tiles/{date}/{layer}/{z}/{x}/{y}.png")
async def tile(date: str, layer: str, z: int, x: int, y: int):
    img_info = database.get_image_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found")
    tile_data = await tile_utils.get_tile(img_info["filename"], z, x, y)
    if tile_data is None:
        empty = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        img_bytes = io.BytesIO()
        empty.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return StreamingResponse(img_bytes, media_type="image/png")
    return StreamingResponse(tile_data, media_type="image/png")

# ИСПРАВЛЕННЫЙ ЭНДПОИНТ СТАТИСТИКИ – читает из БД
@app.get("/api/statistics/{date}/{layer}")
async def get_layer_statistics(date: str, layer: str):
    stats = database.get_statistics_for_layer(date, layer)
    if not stats:
        raise HTTPException(status_code=404, detail="Statistics not found")
    return stats

@app.post("/api/compare")
async def compare_layers(request: dict):
    date1 = request.get("date1")
    layer1 = request.get("layer1")
    date2 = request.get("date2")
    layer2 = request.get("layer2")
    if not date1 or not layer1 or not date2 or not layer2:
        raise HTTPException(status_code=400, detail="Missing parameters")
    stats1 = await get_layer_statistics(date1, layer1)
    stats2 = await get_layer_statistics(date2, layer2)
    return {
        "layer1": {"date": date1, "layer": layer1, "statistics": stats1},
        "layer2": {"date": date2, "layer": layer2, "statistics": stats2}
    }

@app.get("/", response_class=HTMLResponse)
async def get_map(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "web_title": WEB_TITLE,
        "color_background": COLOR_BACKGROUND,
        "color_controls_bg": COLOR_CONTROLS_BG,
        "color_button": COLOR_BUTTON,
        "color_button_hover": COLOR_BUTTON_HOVER,
        "color_select_bg": COLOR_SELECT_BG,
        "color_select_hover": COLOR_SELECT_HOVER,
        "color_text_light": COLOR_TEXT_LIGHT,
        "map_height": MAP_HEIGHT,
        "map_height_mobile": MAP_HEIGHT_MOBILE,
        "controls_padding": CONTROLS_PADDING,
        "default_opacity": DEFAULT_OPACITY,
        "default_map_zoom": DEFAULT_MAP_ZOOM,
        "default_map_center": DEFAULT_MAP_CENTER,
        "max_zoom_tiles": MAX_ZOOM_TILES,
        "enable_compare": ENABLE_COMPARE,
        "base_tile_url": DEFAULT_BASE_TILE_URL,
        "base_attribution": DEFAULT_BASE_ATTRIBUTION,
        "base_max_zoom": DEFAULT_BASE_MAX_ZOOM
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)