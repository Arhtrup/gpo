from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import sqlite3
from datetime import datetime
import json
import rasterio
from rasterio.warp import transform_bounds, reproject, Resampling
import numpy as np
from PIL import Image
import io
import database
from geotiff_parser import parse_geotiff_metadata, guess_crs_from_filename
from logger import app_logger
from settings import (
    IMAGES_DIR, PRODUCT_SUBDIRS, DB_INIT_TABLE, WEB_TITLE,
    COLOR_BACKGROUND, COLOR_CONTROLS_BG, COLOR_BUTTON, COLOR_BUTTON_HOVER,
    COLOR_SELECT_BG, COLOR_SELECT_HOVER, COLOR_TEXT_LIGHT,
    MAP_HEIGHT, MAP_HEIGHT_MOBILE, CONTROLS_PADDING,
    DEFAULT_OPACITY, DEFAULT_MAP_ZOOM, DEFAULT_MAP_CENTER,
    HOST, PORT, ENABLE_COMPARE, COMPARE_SHOW_HISTOGRAMS, COMPARE_HISTOGRAM_BINS,
    DEFAULT_BASE_TILE_URL, DEFAULT_BASE_ATTRIBUTION, DEFAULT_BASE_MAX_ZOOM,
    TEMPLATES_DIR, CORS_ALLOW_ORIGINS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS,
    LAYER_LABELS, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT, IMAGE_QUALITY
)
from models import SatelliteImageInfo

app_logger.info("Запуск спутникового просмотрщика (режим полного изображения)")

if DB_INIT_TABLE:
    database.init_db()

def migrate_crs():
    conn = sqlite3.connect(database.DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, crs FROM images WHERE crs IS NULL")
    rows = c.fetchall()
    updated = 0
    for filename, _ in rows:
        guessed = guess_crs_from_filename(filename)
        if guessed:
            c.execute("UPDATE images SET crs = ? WHERE filename = ?", (guessed, filename))
            updated += 1
            app_logger.info(f"Обновлён CRS для {filename} -> {guessed}")
    conn.commit()
    conn.close()
    app_logger.info(f"Миграция CRS завершена, обновлено записей: {updated}")

migrate_crs()

def compute_histogram(filepath: str, bins=50) -> list:
    try:
        with rasterio.open(filepath) as src:
            data = src.read(1)
            if src.nodata is not None:
                data = data[data != src.nodata]
            data = data[~np.isnan(data)]
            if data.size == 0:
                return []
            hist, _ = np.histogram(data, bins=bins)
            return hist.tolist()
    except Exception as e:
        app_logger.error(f"Ошибка вычисления гистограммы для {filepath}: {e}")
        return []

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
                histogram = compute_histogram(filepath, COMPARE_HISTOGRAM_BINS) if COMPARE_SHOW_HISTOGRAMS else None
            except Exception as e:
                app_logger.error(f"Ошибка чтения метаданных {filepath}: {e}")
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
                stddev=meta['stddev'],
                histogram=histogram
            )
            database.add_image(info)
            app_logger.info(f"Добавлено в БД: {rel_path}")
    app_logger.info("Сканирование завершено")

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
    return database.get_all_dates()

@app.get("/api/layers/{date}")
async def get_layers(date: str):
    layers = database.get_layers_for_date(date)
    for l in layers:
        l["label"] = LAYER_LABELS.get(l["layer"], l["layer"])
    return layers

@app.get("/api/image/{date}/{layer}")
async def get_full_image(date: str, layer: str):
    """Возвращает полноразмерное изображение (PNG) после ресемплинга до разумных размеров"""
    img_info = database.get_image_info_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found")
    if not img_info.get("crs"):
        raise HTTPException(status_code=400, detail="CRS not defined for this layer")
    
    filepath = os.path.join(IMAGES_DIR, img_info["filename"])
    try:
        with rasterio.open(filepath) as src:
            # Читаем все каналы (1 или 3)
            if src.count == 1:
                data = src.read(1)
                # Нормализация
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                data = np.nan_to_num(data, nan=0.0)
                if data.max() - data.min() > 1e-6:
                    data = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
                else:
                    data = np.zeros_like(data, dtype=np.uint8)
                img = Image.fromarray(data, mode='L').convert('RGB')
            elif src.count >= 3:
                data = src.read([1, 2, 3])
                data = data.astype(np.float32)
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                data = np.nan_to_num(data, nan=0.0)
                dmin, dmax = data.min(), data.max()
                if dmax - dmin > 1e-6:
                    data = (data - dmin) / (dmax - dmin) * 255
                else:
                    data = np.zeros_like(data)
                data = data.astype(np.uint8)
                data = np.moveaxis(data, 0, -1)  # (H, W, 3)
                img = Image.fromarray(data, mode='RGB')
            else:
                raise HTTPException(status_code=500, detail="Unsupported band count")
            
            # Ресемплинг, если изображение слишком большое
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                ratio = min(MAX_IMAGE_WIDTH / img.width, MAX_IMAGE_HEIGHT / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.BILINEAR)
            
            # Сохраняем в PNG (прозрачность не нужна)
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            return StreamingResponse(img_bytes, media_type="image/png")
    except Exception as e:
        app_logger.error(f"Ошибка генерации изображения для {filepath}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
        "layer1": {"date": date1, "layer": layer1, "statistics": stats1, "label": LAYER_LABELS.get(layer1, layer1)},
        "layer2": {"date": date2, "layer": layer2, "statistics": stats2, "label": LAYER_LABELS.get(layer2, layer2)}
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
        "default_opacity": DEFAULT_OPACITY / 100.0,
        "default_map_zoom": DEFAULT_MAP_ZOOM,
        "default_map_center": DEFAULT_MAP_CENTER,
        "enable_compare": ENABLE_COMPARE,
        "show_histograms": COMPARE_SHOW_HISTOGRAMS,
        "default_base_tile_url": DEFAULT_BASE_TILE_URL,
        "default_base_attribution": DEFAULT_BASE_ATTRIBUTION,
        "default_base_max_zoom": DEFAULT_BASE_MAX_ZOOM,
        "layer_labels": LAYER_LABELS
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)