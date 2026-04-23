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
from rasterio.windows import Window
import numpy as np
from PIL import Image
import io
import base64
import database
from geotiff_parser import parse_geotiff_metadata, guess_crs_from_filename
from logger import app_logger
from settings import (
    IMAGES_DIR, PRODUCT_SUBDIRS, DB_INIT_TABLE, WEB_TITLE,
    COLOR_BACKGROUND, COLOR_CONTROLS_BG, COLOR_BUTTON, COLOR_BUTTON_HOVER,
    COLOR_SELECT_BG, COLOR_SELECT_HOVER, COLOR_TEXT_LIGHT,
    MAP_HEIGHT, MAP_HEIGHT_MOBILE, CONTROLS_PADDING,
    DEFAULT_OPACITY, DEFAULT_MAP_ZOOM, DEFAULT_MAP_CENTER,
    HOST, PORT, ENABLE_COMPARE, COMPARE_SHOW_HISTOGRAMS, COMPARE_HISTOGRAM_BINS, COMPARE_AREA_SIZE,
    DEFAULT_BASE_TILE_URL, DEFAULT_BASE_ATTRIBUTION, DEFAULT_BASE_MAX_ZOOM,
    TEMPLATES_DIR, CORS_ALLOW_ORIGINS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS,
    LAYER_LABELS, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT
)
from models import SatelliteImageInfo

app_logger.info("Запуск спутникового просмотрщика (режим полного изображения)")

if DB_INIT_TABLE:
    database.init_db()

def migrate_crs():
    try:
        conn = sqlite3.connect(database.DATABASE_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(images)")
        columns = [col[1] for col in c.fetchall()]
        if 'crs' not in columns:
            app_logger.warning("Колонка crs отсутствует, миграция не требуется")
            conn.close()
            return
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
    except Exception as e:
        app_logger.error(f"Ошибка миграции CRS: {e}")

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
    img_info = database.get_image_info_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found")
    if not img_info.get("crs"):
        raise HTTPException(status_code=400, detail="CRS not defined for this layer")
    
    filepath = os.path.join(IMAGES_DIR, img_info["filename"])
    try:
        with rasterio.open(filepath) as src:
            if src.count == 1:
                data = src.read(1)
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                data = np.nan_to_num(data, nan=0.0)
                if data.max() - data.min() > 1e-6:
                    data = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
                else:
                    data = np.zeros_like(data, dtype=np.uint8)
                img = Image.fromarray(data, mode='L').convert('RGB')
            elif src.count >= 3:
                data = src.read([1, 2, 3]).astype(np.float32)
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                data = np.nan_to_num(data, nan=0.0)
                for i in range(3):
                    ch = data[i]
                    ch_min, ch_max = ch.min(), ch.max()
                    if ch_max - ch_min > 1e-6:
                        data[i] = (ch - ch_min) / (ch_max - ch_min) * 255
                    else:
                        data[i] = np.zeros_like(ch)
                data = data.astype(np.uint8)
                data = np.moveaxis(data, 0, -1)
                img = Image.fromarray(data, mode='RGB')
            else:
                raise HTTPException(status_code=500, detail="Unsupported band count")
            
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                ratio = min(MAX_IMAGE_WIDTH / img.width, MAX_IMAGE_HEIGHT / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.BILINEAR)
            
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
        return {"min": None, "max": None, "mean": None, "stddev": None, "histogram": None}
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

def extract_image_from_bbox(filepath, bbox_wgs84, target_size):
    with rasterio.open(filepath) as src:
        if not src.crs:
            raise ValueError(f"No CRS for {filepath}")
        left, bottom, right, top = bbox_wgs84
        bounds_src = transform_bounds("EPSG:4326", src.crs, left, bottom, right, top)
        window = src.window(*bounds_src)
        window = window.round_lengths().round_offsets()
        window = window.intersection(Window(0, 0, src.width, src.height))
        if window.width == 0 or window.height == 0:
            return None
        if src.count == 1:
            data = src.read(1, window=window).astype(np.float32)
        else:
            data = src.read(window=window).astype(np.float32)
            data = np.mean(data, axis=0)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        data = np.nan_to_num(data, nan=0.0)
        dmin, dmax = data.min(), data.max()
        if dmax - dmin > 1e-6:
            data = ((data - dmin) / (dmax - dmin) * 255).astype(np.uint8)
        else:
            data = np.zeros_like(data, dtype=np.uint8)
        if data.shape != target_size:
            img = Image.fromarray(data)
            img = img.resize(target_size, Image.Resampling.BILINEAR)
            data = np.array(img)
        return data

@app.post("/api/compare-area")
async def compare_area(request: dict):
    date1 = request.get("date1")
    layer1 = request.get("layer1")
    date2 = request.get("date2")
    layer2 = request.get("layer2")
    bbox = request.get("bbox")
    if not all([date1, layer1, date2, layer2, bbox]) or len(bbox) != 4:
        raise HTTPException(status_code=400, detail="Missing parameters or invalid bbox")
    
    img_info1 = database.get_image_info_by_layer_and_date(date1, layer1)
    img_info2 = database.get_image_info_by_layer_and_date(date2, layer2)
    if not img_info1 or not img_info2:
        raise HTTPException(status_code=404, detail="Layer not found")
    
    filepath1 = os.path.join(IMAGES_DIR, img_info1["filename"])
    filepath2 = os.path.join(IMAGES_DIR, img_info2["filename"])
    
    try:
        target_size = COMPARE_AREA_SIZE
        data1 = extract_image_from_bbox(filepath1, bbox, target_size)
        data2 = extract_image_from_bbox(filepath2, bbox, target_size)
        if data1 is None or data2 is None:
            raise HTTPException(status_code=400, detail="Selected area is outside the image bounds")
        
        diff = np.abs(data1.astype(np.float32) - data2.astype(np.float32))
        diff_min = float(np.min(diff))
        diff_max = float(np.max(diff))
        diff_mean = float(np.mean(diff))
        diff_std = float(np.std(diff))
        hist, _ = np.histogram(diff, bins=50, range=(0, 255))
        
        diff_img = Image.fromarray(diff.astype(np.uint8), mode='L').convert('RGB')
        img_bytes = io.BytesIO()
        diff_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
        
        return {
            "statistics": {
                "min": diff_min,
                "max": diff_max,
                "mean": diff_mean,
                "stddev": diff_std,
                "histogram": hist.tolist()
            },
            "image": f"data:image/png;base64,{img_base64}"
        }
    except Exception as e:
        app_logger.error(f"Ошибка сравнения областей: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
        "default_opacity_percent": DEFAULT_OPACITY,
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