from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from datetime import datetime
import json
import rasterio
import io
import database
import tile_utils
from geotiff_parser import parse_geotiff_metadata
from settings import (
    IMAGES_DIR, PRODUCT_SUBDIRS, DB_INIT_TABLE, WEB_TITLE,
    COLOR_BACKGROUND, COLOR_CONTROLS_BG, COLOR_BUTTON, COLOR_BUTTON_HOVER,
    COLOR_SELECT_BG, COLOR_SELECT_HOVER, COLOR_TEXT_LIGHT,
    MAP_HEIGHT, MAP_HEIGHT_MOBILE, CONTROLS_PADDING,
    DEFAULT_OPACITY, DEFAULT_MAP_ZOOM, DEFAULT_MAP_CENTER, MAX_ZOOM_TILES,
    HOST, PORT, ENABLE_COMPARE
)
from models import SatelliteImageInfo

# ------------------- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И МИГРАЦИЯ -------------------
if DB_INIT_TABLE:
    database.init_db()   # создаёт таблицу и добавляет недостающие колонки

def migrate_existing_records():
    """Обновляет старые записи, у которых отсутствуют метаданные (crs, width и т.д.)"""
    conn = sqlite3.connect(database.DATABASE_PATH)
    c = conn.cursor()
    # Выбираем записи, где хотя бы одно из новых полей NULL
    c.execute("SELECT filename FROM images WHERE crs IS NULL OR width IS NULL OR height IS NULL")
    rows = c.fetchall()
    for (filename,) in rows:
        filepath = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            continue
        try:
            meta = parse_geotiff_metadata(filepath)
            c.execute("""
                UPDATE images 
                SET crs = ?, width = ?, height = ?, 
                    min_value = ?, max_value = ?, mean_value = ?, stddev = ?
                WHERE filename = ?
            """, (meta['crs'], meta['width'], meta['height'],
                  meta['min_value'], meta['max_value'], meta['mean_value'], meta['stddev'],
                  filename))
        except Exception as e:
            print(f"Migration error for {filename}: {e}")
    conn.commit()
    conn.close()
    print(f"Migrated {len(rows)} records with missing metadata.")

# Запускаем миграцию, если в БД уже есть записи
if database.get_all_dates():
    migrate_existing_records()

# ------------------- ЗАПОЛНЕНИЕ БАЗЫ НОВЫМИ ФАЙЛАМИ -------------------
def parse_filename(filename):
    """Парсит имя файла: ожидается tile_id_YYYYMMDDThhmmss.ext"""
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

# Если база пуста – заполняем из файлов
if not database.get_all_dates():
    for product_type in PRODUCT_SUBDIRS:
        product_dir = os.path.join(IMAGES_DIR, product_type)
        if not os.path.isdir(product_dir):
            continue
        for fname in os.listdir(product_dir):
            if fname.lower().endswith(('.tiff', '.tif')):
                parsed = parse_filename(fname)
                if parsed is None:
                    print(f"Skipping {fname}: cannot parse filename")
                    continue
                tile_id, dt = parsed
                filepath = os.path.join(product_dir, fname)
                try:
                    meta = parse_geotiff_metadata(filepath)
                except Exception as e:
                    print(f"Warning: Could not read GeoTIFF metadata for {filepath}: {e}")
                    # fallback: минимальные данные
                    with rasterio.open(filepath) as src:
                        bounds = src.bounds
                        crs = src.crs.to_string() if src.crs else None
                        width, height = src.width, src.height
                    meta = {
                        'bounds': bounds,
                        'crs': crs,
                        'width': width,
                        'height': height,
                        'min_value': None,
                        'max_value': None,
                        'mean_value': None,
                        'stddev': None
                    }

                rel_path = os.path.join(product_type, fname)
                info = SatelliteImageInfo(
                    filename=rel_path,
                    date=dt,
                    layer_type=product_type,
                    bounds=meta['bounds'],
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
                print(f"Added {rel_path} to database.")

# ------------------- FASTAPI ПРИЛОЖЕНИЕ -------------------
app = FastAPI(title=WEB_TITLE)
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dates", response_model=list[str])
async def get_dates():
    """Список всех доступных дат в формате YYYY-MM-DD"""
    return database.get_all_dates()

@app.get("/api/layers/{date}")
async def get_layers(date: str):
    """Список доступных слоёв для указанной даты"""
    layers = database.get_layers_for_date(date)
    return layers

@app.get("/tiles/{date}/{layer}/{z}/{x}/{y}.png")
async def tile(date: str, layer: str, z: int, x: int, y: int):
    """Отдача тайла для конкретной даты и слоя"""
    img_info = database.get_image_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found for this date")

    tile_data = await tile_utils.get_tile(img_info["filename"], z, x, y)
    if tile_data is None:
        from PIL import Image
        empty = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        img_bytes = io.BytesIO()
        empty.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return StreamingResponse(img_bytes, media_type="image/png")

    return StreamingResponse(tile_data, media_type="image/png")

@app.get("/api/statistics/{date}/{layer}")
async def get_layer_statistics(date: str, layer: str):
    """Статистика по слою для указанной даты"""
    img_info = database.get_image_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found")
    filepath = os.path.join(IMAGES_DIR, img_info["filename"])
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    stats = tile_utils.get_statistics(filepath)
    if stats is None:
        raise HTTPException(status_code=500, detail="Could not read statistics")
    return stats

@app.post("/api/compare")
async def compare_layers(request: dict):
    """Сравнение двух слоёв (дата1/слой1 и дата2/слой2)"""
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
    """Страница с картой и панелью управления + панель сравнения"""
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
        "enable_compare": ENABLE_COMPARE
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)