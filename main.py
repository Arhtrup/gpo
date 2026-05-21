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
from PIL import Image, ImageOps, ImageFilter
import math
import io
import base64
import database
from fastapi.responses import JSONResponse
import base64
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

def fix_missing_crs():
    try:
        conn = sqlite3.connect(database.DATABASE_PATH)
        c = conn.cursor()
        # Найти все записи с NULL CRS
        c.execute("SELECT filename FROM images WHERE crs IS NULL")
        rows = c.fetchall()
        updated = 0
        for (filename,) in rows:
            # Извлечь имя файла без пути
            base_filename = os.path.basename(filename)
            guessed = guess_crs_from_filename(base_filename)
            if guessed:
                c.execute("UPDATE images SET crs = ? WHERE filename = ?", (guessed, filename))
                updated += 1
                app_logger.info(f"Обновлён CRS для {filename} -> {guessed}")
            else:
                # Если не удалось определить, установить CRS по умолчанию для зоны 45
                if 'T45' in base_filename:
                    c.execute("UPDATE images SET crs = ? WHERE filename = ?", ("EPSG:32745", filename))
                    updated += 1
                    app_logger.info(f"Принудительно установлен CRS EPSG:32745 для {filename}")
        conn.commit()
        conn.close()
        app_logger.info(f"Исправление CRS завершено, обновлено записей: {updated}")
    except Exception as e:
        app_logger.error(f"Ошибка исправления CRS: {e}")

migrate_crs()
fix_missing_crs()

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
                transform=meta.get('transform'),  # Добавляем
                is_rotated=meta.get('is_rotated', False),  # Добавляем
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
            height = src.height
            width = src.width
            
            # Получаем оригинальные границы в WGS84
            if img_info.get("bounds"):
                original_bounds = img_info["bounds"]
            else:
                bounds = src.bounds
                if src.crs:
                    original_bounds = transform_bounds(src.crs, 'EPSG:4326', *bounds)
                else:
                    original_bounds = bounds
            
            # Читаем и обрабатываем изображение
            if src.count == 1:
                data = src.read(1)
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                
                valid_mask = ~np.isnan(data)
                
                data = np.nan_to_num(data, nan=0.0)
                if data.max() - data.min() > 1e-6:
                    data = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
                else:
                    data = np.zeros_like(data, dtype=np.uint8)
                
                img = Image.fromarray(data, mode='L').convert('RGBA')
                img_array = np.array(img)
                img_array[~valid_mask, 3] = 0
                img = Image.fromarray(img_array, mode='RGBA')
                
            elif src.count >= 3:
                data = src.read([1, 2, 3]).astype(np.float32)
                if src.nodata is not None:
                    data = np.where(data == src.nodata, np.nan, data)
                
                valid_mask = ~np.isnan(data).any(axis=0)
                
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
                
                img = Image.fromarray(data, mode='RGB').convert('RGBA')
                img_array = np.array(img)
                img_array[~valid_mask, 3] = 0
                img = Image.fromarray(img_array, mode='RGBA')
            else:
                raise HTTPException(status_code=500, detail="Unsupported band count")
            
            # Получаем углы изображения в географических координатах
            corners_pixel = [(0, 0), (width, 0), (width, height), (0, height)]
            corners_geo = []
            for col, row in corners_pixel:
                x, y = src.transform * (col, row)
                if src.crs:
                    lon, lat = transform_bounds(src.crs, 'EPSG:4326', x, y, x, y)[:2]
                else:
                    lon, lat = x, y
                corners_geo.append((lon, lat))
            
            # Вычисляем угол поворота
            dx = corners_geo[1][0] - corners_geo[0][0]
            dy = corners_geo[1][1] - corners_geo[0][1]
            angle = math.degrees(math.atan2(dy, dx))
            
            app_logger.info(f"Оригинальные границы WGS84: {original_bounds}")
            app_logger.info(f"Углы WGS84: {corners_geo}")
            app_logger.info(f"Расчётный угол поворота: {angle} градусов")
            app_logger.info(f"Оригинальный размер изображения: {img.size}")
            
            # Запоминаем оригинальный размер
            original_size = img.size
            
            # Применяем поворот, если необходимо
            if abs(angle) > 1.0 and abs(angle - 90) > 1.0 and abs(angle + 90) > 1.0:
                app_logger.info(f"Поворачиваем изображение на {angle} градусов")
                
                # Поворачиваем с expand=True, фон будет прозрачным
                img = img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
                app_logger.info(f"Размер после поворота: {img.size}")
                
                # Обрезаем прозрачные края
                alpha = np.array(img.getchannel("A"))
                mask = alpha > 10

                coords = np.argwhere(mask)

                if coords.size > 0:
                    y0, x0 = coords.min(axis=0)
                    y1, x1 = coords.max(axis=0) + 1
                    img = img.crop((x0, y0, x1, y1))
                    app_logger.info(f"Размер после обрезки: {img.size}")
                #if bbox:
                #    img = img.crop(bbox)
                #    app_logger.info(f"Размер после обрезки: {img.size}")
                
                # Масштабируем обратно до оригинального размера
                if img.size != original_size:
                    app_logger.info(f"resize from {img.size} to {original_size}")

                    img = img.resize(
                        original_size,
                        Image.Resampling.BILINEAR
                    )

                    app_logger.info(f"after resize: {img.size}")
                
                # Пересчитываем границы для повернутого изображения с учетом центрирования
                # Находим центр оригинального изображения
                center_lon = (original_bounds[0] + original_bounds[2]) / 2
                center_lat = (original_bounds[1] + original_bounds[3]) / 2
                
                # Половины размеров в градусах
                half_width = (original_bounds[2] - original_bounds[0]) / 2
                half_height = (original_bounds[3] - original_bounds[1]) / 2
                
                # Углы относительно центра
                corners_rel = [
                    (-half_width, -half_height),  # верхний-левый
                    ( half_width, -half_height),  # верхний-правый
                    ( half_width,  half_height),  # нижний-правый
                    (-half_width,  half_height)   # нижний-левый
                ]
                
                # Поворачиваем углы
                rad = math.radians(angle)
                cos_a = math.cos(rad)
                sin_a = math.sin(rad)
                
                rotated_corners = []
                for x, y in corners_rel:
                    x_rot = x * cos_a - y * sin_a
                    y_rot = x * sin_a + y * cos_a
                    rotated_corners.append((center_lon + x_rot, center_lat + y_rot))
                
                # Новые границы
                new_bounds = [
                    min(c[0] for c in rotated_corners),  # min lon (west)
                    min(c[1] for c in rotated_corners),  # min lat (south)
                    max(c[0] for c in rotated_corners),  # max lon (east)
                    max(c[1] for c in rotated_corners)   # max lat (north)
                ]
                
                app_logger.info(f"Новые границы после поворота: {new_bounds}")
                response_bounds = original_bounds
            else:
                app_logger.info(f"Поворот не требуется (угол {angle} градусов)")
                response_bounds = original_bounds
            
            # Изменяем размер при необходимости (если превышает лимиты)
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                ratio = min(MAX_IMAGE_WIDTH / img.width, MAX_IMAGE_HEIGHT / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.BILINEAR)
                app_logger.info(f"Размер после ресайза для лимитов: {img.size}")
            
            # Сохраняем изображение в bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # Кодируем изображение в base64 для передачи вместе с границами
            img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
            
            return JSONResponse({
                "image": f"data:image/png;base64,{img_base64}",
                "bounds": response_bounds
            })
            
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
    
    # Вычисляем изменения между слоями
    changes = {}
    if stats1 and stats2 and stats1.get('mean') is not None and stats2.get('mean') is not None:
        changes['mean_change'] = stats2['mean'] - stats1['mean']
        changes['mean_change_percent'] = (changes['mean_change'] / stats1['mean']) * 100 if stats1['mean'] != 0 else 0
        changes['min_change'] = stats2['min'] - stats1['min'] if stats1['min'] is not None else None
        changes['max_change'] = stats2['max'] - stats1['max'] if stats1['max'] is not None else None
    
    return {
        "layer1": {
            "date": date1, 
            "layer": layer1, 
            "statistics": stats1, 
            "label": LAYER_LABELS.get(layer1, layer1)
        },
        "layer2": {
            "date": date2, 
            "layer": layer2, 
            "statistics": stats2, 
            "label": LAYER_LABELS.get(layer2, layer2)
        },
        "changes": changes
    }

def extract_image_from_bbox(filepath, bbox_wgs84, target_size):
    """Извлекает область изображения по WGS84 координатам"""
    try:
        app_logger.info(f"Извлечение области из {filepath}, bbox={bbox_wgs84}")
        
        with rasterio.open(filepath) as src:
            app_logger.info(f"Размер изображения: {src.width}x{src.height}, CRS={src.crs}")
            
            # Получаем CRS (не пытаемся его изменить!)
            crs = src.crs
            if not crs:
                # Если CRS нет, пытаемся определить из имени файла
                base_filename = os.path.basename(filepath)
                guessed_crs = guess_crs_from_filename(base_filename)
                if guessed_crs:
                    from rasterio.crs import CRS
                    crs = CRS.from_string(guessed_crs)
                    app_logger.warning(f"Определен CRS из имени файла для {filepath}: {guessed_crs}")
                else:
                    if 'T45' in base_filename:
                        from rasterio.crs import CRS
                        crs = CRS.from_string("EPSG:32745")
                        app_logger.warning(f"Принудительно установлен CRS EPSG:32745 для {filepath}")
                    else:
                        raise ValueError(f"No CRS for {filepath}")
            else:
                app_logger.info(f"Используем CRS из файла: {crs}")
            
            left, bottom, right, top = bbox_wgs84
            app_logger.info(f"WGS84 границы: left={left}, bottom={bottom}, right={right}, top={top}")
            
            # Преобразуем WGS84 границы в CRS изображения
            try:
                bounds_src = transform_bounds("EPSG:4326", crs, left, bottom, right, top)
                app_logger.info(f"Границы в CRS изображения: {bounds_src}")
            except Exception as e:
                app_logger.error(f"Ошибка преобразования границ: {e}")
                return None
            
            # Получаем окно в пикселях
            window = src.window(*bounds_src)
            window = window.round_lengths().round_offsets()
            window = window.intersection(Window(0, 0, src.width, src.height))
            
            app_logger.info(f"Окно: {window}")
            
            if window.width == 0 or window.height == 0:
                app_logger.warning("Окно за пределами изображения")
                return None
            
            # Читаем данные
            if src.count == 1:
                data = src.read(1, window=window).astype(np.float32)
                app_logger.info(f"Прочитан 1 канал, форма={data.shape}")
            else:
                # Для многоканальных изображений используем среднее
                bands_to_read = min(3, src.count)
                data = src.read(list(range(1, bands_to_read + 1)), window=window).astype(np.float32)
                data = np.mean(data, axis=0)
                app_logger.info(f"Прочитано {bands_to_read} каналов, после среднего форма={data.shape}")
            
            # Обрабатываем nodata значения
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)
            
            # Заменяем NaN на 0
            data = np.nan_to_num(data, nan=0.0)
            
            # Нормализуем данные в диапазон 0-255
            dmin, dmax = data.min(), data.max()
            app_logger.info(f"Диапазон данных: min={dmin}, max={dmax}")
            
            if dmax - dmin > 1e-6:
                data = ((data - dmin) / (dmax - dmin) * 255).astype(np.uint8)
            else:
                data = np.zeros_like(data, dtype=np.uint8)
            
            # Изменяем размер до целевого
            if data.shape[0] != target_size[1] or data.shape[1] != target_size[0]:
                img = Image.fromarray(data)
                img = img.resize(target_size, Image.Resampling.BILINEAR)
                data = np.array(img)
                app_logger.info(f"Изменен размер на {data.shape}")
            
            return data
            
    except Exception as e:
        app_logger.error(f"Ошибка в extract_image_from_bbox: {e}", exc_info=True)
        return None


@app.post("/api/compare-area")
async def compare_area(request: dict):
    try:
        date1 = request.get("date1")
        layer1 = request.get("layer1")
        date2 = request.get("date2")
        layer2 = request.get("layer2")
        bbox = request.get("bbox")
        
        app_logger.info(f"=== СРАВНЕНИЕ ОБЛАСТЕЙ ===")
        app_logger.info(f"date1={date1}, layer1={layer1}")
        app_logger.info(f"date2={date2}, layer2={layer2}")
        app_logger.info(f"bbox={bbox}")
        
        if not all([date1, layer1, date2, layer2, bbox]) or len(bbox) != 4:
            raise HTTPException(status_code=400, detail="Missing parameters or invalid bbox")
        
        # Получаем информацию об изображениях
        img_info1 = database.get_image_info_by_layer_and_date(date1, layer1)
        img_info2 = database.get_image_info_by_layer_and_date(date2, layer2)
        
        app_logger.info(f"img_info1: {img_info1}")
        app_logger.info(f"img_info2: {img_info2}")
        
        if not img_info1 or not img_info2:
            raise HTTPException(status_code=404, detail="Layer not found")
        
        filepath1 = os.path.join(IMAGES_DIR, img_info1["filename"])
        filepath2 = os.path.join(IMAGES_DIR, img_info2["filename"])
        
        app_logger.info(f"filepath1: {filepath1}")
        app_logger.info(f"filepath2: {filepath2}")
        
        # Проверяем существование файлов
        if not os.path.exists(filepath1):
            raise HTTPException(status_code=404, detail=f"File not found: {filepath1}")
        if not os.path.exists(filepath2):
            raise HTTPException(status_code=404, detail=f"File not found: {filepath2}")
        
        target_size = COMPARE_AREA_SIZE  # (256, 256)
        
        # Извлекаем данные для выбранной области
        data1 = extract_image_from_bbox(filepath1, bbox, target_size)
        data2 = extract_image_from_bbox(filepath2, bbox, target_size)
        
        app_logger.info(f"data1 is None: {data1 is None}")
        app_logger.info(f"data2 is None: {data2 is None}")
        
        if data1 is None or data2 is None:
            raise HTTPException(status_code=400, detail="Selected area is outside the image bounds")
        
        # Вычисляем разницу
        diff = np.abs(data1.astype(np.float32) - data2.astype(np.float32))
        
        # Статистика разницы
        diff_min = float(np.min(diff))
        diff_max = float(np.max(diff))
        diff_mean = float(np.mean(diff))
        diff_std = float(np.std(diff))
        hist, _ = np.histogram(diff, bins=50, range=(0, 255))
        
        # Статистика для первого изображения
        stats1_min = float(np.min(data1))
        stats1_max = float(np.max(data1))
        stats1_mean = float(np.mean(data1))
        stats1_std = float(np.std(data1))
        
        # Статистика для второго изображения
        stats2_min = float(np.min(data2))
        stats2_max = float(np.max(data2))
        stats2_mean = float(np.mean(data2))
        stats2_std = float(np.std(data2))
        
        # Изменения
        mean_change = stats2_mean - stats1_mean
        mean_change_percent = (mean_change / stats1_mean * 100) if stats1_mean != 0 else 0
        
        # Создаем изображение разницы
        diff_img = Image.fromarray(diff.astype(np.uint8), mode='L').convert('RGB')
        img_bytes = io.BytesIO()
        diff_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
        
        # Создаем изображения для каждого слоя
        img1 = Image.fromarray(data1, mode='L')
        img1_bytes = io.BytesIO()
        img1.save(img1_bytes, format='PNG')
        img1_base64 = base64.b64encode(img1_bytes.getvalue()).decode('utf-8')
        
        img2 = Image.fromarray(data2, mode='L')
        img2_bytes = io.BytesIO()
        img2.save(img2_bytes, format='PNG')
        img2_base64 = base64.b64encode(img2_bytes.getvalue()).decode('utf-8')
        
        response_data = {
            "statistics": {
                "min": diff_min,
                "max": diff_max,
                "mean": diff_mean,
                "stddev": diff_std,
                "histogram": hist.tolist()
            },
            "layer1_stats": {
                "min": stats1_min,
                "max": stats1_max,
                "mean": stats1_mean,
                "stddev": stats1_std
            },
            "layer2_stats": {
                "min": stats2_min,
                "max": stats2_max,
                "mean": stats2_mean,
                "stddev": stats2_std
            },
            "changes": {
                "mean_change": mean_change,
                "mean_change_percent": mean_change_percent
            },
            "images": {
                "diff": f"data:image/png;base64,{img_base64}",
                "layer1": f"data:image/png;base64,{img1_base64}",
                "layer2": f"data:image/png;base64,{img2_base64}"
            }
        }
        
        app_logger.info("Ответ успешно сформирован")
        return response_data
        
    except HTTPException:
        raise
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