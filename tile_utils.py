import rasterio
from rasterio.warp import transform_bounds
from rasterio.plot import reshape_as_image
from PIL import Image
import numpy as np
import io
import os
from settings import IMAGES_DIR

def tile_to_latlon(xtile, ytile, zoom):
    """Конвертация XYZ тайла в координаты углов (EPSG:4326)"""
    n = 2.0 ** zoom
    lon_deg_left = xtile / n * 360.0 - 180.0
    lon_deg_right = (xtile + 1) / n * 360.0 - 180.0
    lat_rad_top = np.arctan(np.sinh(np.pi * (1 - 2 * ytile / n)))
    lat_rad_bottom = np.arctan(np.sinh(np.pi * (1 - 2 * (ytile + 1) / n)))
    lat_deg_top = np.degrees(lat_rad_top)
    lat_deg_bottom = np.degrees(lat_rad_bottom)
    return (lon_deg_left, lat_deg_bottom, lon_deg_right, lat_deg_top)  # (minx, miny, maxx, maxy)

async def get_tile(filename: str, zoom: int, x: int, y: int):
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        return None

    tile_bounds = tile_to_latlon(x, y, zoom)  # (left, bottom, right, top)

    with rasterio.open(filepath) as src:
        try:
            window = src.window(*tile_bounds)
        except Exception:
            return None

        if window.col_off < 0 or window.row_off < 0 or \
           window.col_off + window.width > src.width or \
           window.row_off + window.height > src.height:
            return None

        data = src.read(window=window, indexes=[1,2,3])
        if data.size == 0:
            return None

        img_array = np.moveaxis(data, 0, -1)

        if img_array.shape[-1] == 1:
            band = img_array[:,:,0]
            band = np.nan_to_num(band, nan=0.0, posinf=1.0, neginf=0.0)
            band_norm = ((band - band.min()) / (band.max() - band.min() + 1e-8) * 255).astype(np.uint8)
            img_array = np.stack([band_norm, band_norm, band_norm], axis=-1)
        img = Image.fromarray(img_array.astype(np.uint8))
        if img.size != (256, 256):
            img = img.resize((256, 256), Image.Resampling.LANCZOS)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes