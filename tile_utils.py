import rasterio
from PIL import Image
import numpy as np
import io
import os
from settings import IMAGES_DIR, TILE_SIZE, STATISTICS_TAGS

def tile_to_latlon(xtile, ytile, zoom):
    """Конвертация XYZ тайла в координаты углов (EPSG:4326)"""
    n = 2.0 ** zoom
    lon_deg_left = xtile / n * 360.0 - 180.0
    lon_deg_right = (xtile + 1) / n * 360.0 - 180.0
    lat_rad_top = np.arctan(np.sinh(np.pi * (1 - 2 * ytile / n)))
    lat_rad_bottom = np.arctan(np.sinh(np.pi * (1 - 2 * (ytile + 1) / n)))
    lat_deg_top = np.degrees(lat_rad_top)
    lat_deg_bottom = np.degrees(lat_rad_bottom)
    return (lon_deg_left, lat_deg_bottom, lon_deg_right, lat_deg_top)

async def get_tile(filename: str, zoom: int, x: int, y: int):
    """Возвращает байты PNG-тайла размером 256x256 или None, если тайл вне изображения."""
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        return None

    tile_bounds = tile_to_latlon(x, y, zoom)

    with rasterio.open(filepath) as src:
        try:
            window = src.window(*tile_bounds)
        except Exception:
            return None

        if window.col_off < 0 or window.row_off < 0 or \
           window.col_off + window.width > src.width or \
           window.row_off + window.height > src.height:
            return None

        bands = src.count
        if bands == 1:
            data = src.read(1, window=window)
            data = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=0.0)
            if data.max() - data.min() > 0:
                data_norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
            else:
                data_norm = np.zeros_like(data, dtype=np.uint8)
            img_array = np.stack([data_norm, data_norm, data_norm], axis=-1)
        elif bands >= 3:
            data = src.read([1, 2, 3], window=window)
            img_array = np.moveaxis(data, 0, -1).astype(np.uint8)
        else:
            return None

        img = Image.fromarray(img_array)
        if img.size != (TILE_SIZE, TILE_SIZE):
            img = img.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

def get_statistics(filepath):
    """Извлечение статистики из GeoTIFF (теги STATISTICS_* или вычисление)"""
    try:
        with rasterio.open(filepath) as src:
            tags = src.tags()
            stats = {}
            for key, tag in STATISTICS_TAGS.items():
                if tag in tags:
                    try:
                        stats[key] = float(tags[tag])
                    except ValueError:
                        stats[key] = None
                else:
                    stats[key] = None
            return stats
    except Exception as e:
        print(f"Error reading statistics from {filepath}: {e}")
        return None