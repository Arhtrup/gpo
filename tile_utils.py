import rasterio
from rasterio.warp import transform_bounds
from PIL import Image
import numpy as np
import io
import os
import functools
from settings import IMAGES_DIR, TILE_SIZE, STATISTICS_TAGS
from logger import app_logger

# Кэш для открытых файлов (ускоряет многократные запросы)
@functools.lru_cache(maxsize=128)
def get_rasterio_dataset(filepath):
    """Открывает и возвращает объект DatasetReader (с автозакрытием не требуется, rasterio сам управляет)"""
    return rasterio.open(filepath)

def tile_to_latlon(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg_left = xtile / n * 360.0 - 180.0
    lon_deg_right = (xtile + 1) / n * 360.0 - 180.0
    lat_rad_top = np.arctan(np.sinh(np.pi * (1 - 2 * ytile / n)))
    lat_rad_bottom = np.arctan(np.sinh(np.pi * (1 - 2 * (ytile + 1) / n)))
    lat_deg_top = np.degrees(lat_rad_top)
    lat_deg_bottom = np.degrees(lat_rad_bottom)
    return (lon_deg_left, lat_deg_bottom, lon_deg_right, lat_deg_top)

async def get_tile(filename: str, zoom: int, x: int, y: int):
    filepath = os.path.join(IMAGES_DIR, filename)
    app_logger.debug(f"Тайл запрос: {filename}, z={zoom}, x={x}, y={y}")

    bounds_wgs84 = tile_to_latlon(x, y, zoom)  # (left, bottom, right, top)
    app_logger.debug(f"Границы тайла в WGS84: {bounds_wgs84}")

    try:
        src = get_rasterio_dataset(filepath)   # используем кэшированное открытие
        if not src.crs:
            app_logger.error(f"Файл {filename} не имеет CRS, тайлы не могут быть сгенерированы")
            return None

        # Преобразуем границы тайла в проекцию файла
        bounds_src = transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        app_logger.debug(f"Границы в CRS {src.crs}: {bounds_src}")

        # Получаем индексы пикселей для прямоугольника bounds_src
        left, bottom, right, top = bounds_src
        col_min, row_min = src.index(left, top)     # src.index(x, y) – x=долгота, y=широта
        col_max, row_max = src.index(right, bottom)
        # Упорядочиваем
        col_start = min(col_min, col_max)
        col_end = max(col_min, col_max) + 1
        row_start = min(row_min, row_max)
        row_end = max(row_min, row_max) + 1

        # Обрезаем по границам изображения
        col_start = max(0, col_start)
        col_end = min(src.width, col_end)
        row_start = max(0, row_start)
        row_end = min(src.height, row_end)

        if col_start >= col_end or row_start >= row_end:
            app_logger.debug(f"Тайл {zoom}/{x}/{y} не пересекается с изображением {filename}")
            return None

        # Чтение данных
        bands = src.count
        if bands == 1:
            data = src.read(1, window=((row_start, row_end), (col_start, col_end)))
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)
            data = np.nan_to_num(data, nan=0.0)
            if data.max() - data.min() > 1e-6:
                data_norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
            else:
                data_norm = np.zeros_like(data, dtype=np.uint8)
            # Создаём полный тайл 256x256 и вставляем прочитанную область
            full_img = np.zeros((TILE_SIZE, TILE_SIZE, 3), dtype=np.uint8)
            # Вычисляем смещение вставки
            offset_row = row_start - (row_min if row_min <= row_max else row_max)
            offset_col = col_start - (col_min if col_min <= col_max else col_max)
            # Масштабируем координаты вставки относительно исходного окна
            # Проще: создаём полный массив и вставляем data_norm в нужную позицию
            # Но data_norm имеет размер (h, w) – вставляем в соответствующие срезы full_img[:,:,0]
            h, w = data_norm.shape
            full_img[offset_row:offset_row+h, offset_col:offset_col+w, 0] = data_norm
            full_img[offset_row:offset_row+h, offset_col:offset_col+w, 1] = data_norm
            full_img[offset_row:offset_row+h, offset_col:offset_col+w, 2] = data_norm
            img = Image.fromarray(full_img)
        elif bands >= 3:
            data = src.read([1,2,3], window=((row_start, row_end), (col_start, col_end)))
            data = data.astype(np.float32)
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)
            # Нормализация каждого канала
            for i in range(3):
                band = data[i]
                band_min, band_max = np.nanmin(band), np.nanmax(band)
                if band_max - band_min > 1e-6:
                    data[i] = (band - band_min) / (band_max - band_min) * 255
                else:
                    data[i] = np.zeros_like(band)
            data = np.nan_to_num(data, nan=0).astype(np.uint8)
            # Транспонируем в (H, W, C)
            img_array = np.moveaxis(data, 0, -1)
            h, w, _ = img_array.shape
            # Вставляем в полный тайл 256x256
            full_img = np.zeros((TILE_SIZE, TILE_SIZE, 3), dtype=np.uint8)
            offset_row = row_start - (row_min if row_min <= row_max else row_max)
            offset_col = col_start - (col_min if col_min <= col_max else col_max)
            full_img[offset_row:offset_row+h, offset_col:offset_col+w, :] = img_array
            img = Image.fromarray(full_img)
        else:
            app_logger.warning(f"Неподдерживаемое число каналов {bands} в {filename}")
            return None

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        app_logger.debug(f"Тайл {zoom}/{x}/{y} успешно сгенерирован")
        return img_bytes
    except Exception as e:
        app_logger.error(f"Ошибка при генерации тайла {zoom}/{x}/{y} для {filename}: {e}", exc_info=True)
        return None

def get_statistics(filepath):
    # Этот метод больше не используется, статистика берётся из БД
    # Оставляем для совместимости, но можно удалить
    return None