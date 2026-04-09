import rasterio
import numpy as np
from rasterio.warp import transform_bounds
from logger import app_logger

def parse_geotiff_metadata(filepath):
    try:
        with rasterio.open(filepath) as src:
            bounds = src.bounds  # (left, bottom, right, top) в CRS файла
            crs = src.crs.to_string() if src.crs else None
            width = src.width
            height = src.height

            # Преобразование границ в WGS84, если есть CRS
            if src.crs:
                try:
                    bounds_wgs84 = transform_bounds(src.crs, 'EPSG:4326', *bounds)
                except Exception as e:
                    app_logger.warning(f"Ошибка преобразования bounds для {filepath}: {e}")
                    bounds_wgs84 = bounds  # fallback
            else:
                bounds_wgs84 = bounds

            tags = src.tags()
            stats = {}
            try:
                stats['min'] = float(tags.get('STATISTICS_MINIMUM', np.nan))
                stats['max'] = float(tags.get('STATISTICS_MAXIMUM', np.nan))
                stats['mean'] = float(tags.get('STATISTICS_MEAN', np.nan))
                stats['stddev'] = float(tags.get('STATISTICS_STDDEV', np.nan))
            except (ValueError, TypeError):
                stats = {'min': np.nan, 'max': np.nan, 'mean': np.nan, 'stddev': np.nan}

            if np.isnan(stats['min']):
                data = src.read(1)
                data = data[~np.isnan(data)]
                if data.size > 0:
                    stats['min'] = float(data.min())
                    stats['max'] = float(data.max())
                    stats['mean'] = float(data.mean())
                    stats['stddev'] = float(data.std())
                    app_logger.debug(f"Статистика вычислена для {filepath}")

            return {
                'bounds': bounds,
                'bounds_wgs84': bounds_wgs84,
                'crs': crs,
                'width': width,
                'height': height,
                'min_value': stats['min'] if not np.isnan(stats['min']) else None,
                'max_value': stats['max'] if not np.isnan(stats['max']) else None,
                'mean_value': stats['mean'] if not np.isnan(stats['mean']) else None,
                'stddev': stats['stddev'] if not np.isnan(stats['stddev']) else None
            }
    except Exception as e:
        app_logger.warning(f"Не удалось прочитать метаданные {filepath}: {e}")
        return {
            'bounds': (-180, -90, 180, 90),
            'bounds_wgs84': (-180, -90, 180, 90),
            'crs': None,
            'width': None,
            'height': None,
            'min_value': None,
            'max_value': None,
            'mean_value': None,
            'stddev': None
        }