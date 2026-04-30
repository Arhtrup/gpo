import rasterio
import numpy as np
from rasterio.warp import transform_bounds
from logger import app_logger
import re
import math

def guess_crs_from_filename(filename: str):
    # Более гибкий паттерн для поиска UTM зоны
    # Ищем T или S, затем 1-2 цифры, затем буквы
    match = re.search(r'[TS](\d{1,2})([A-Z]+)', filename)
    if match:
        zone = int(match.group(1))
        lat_band = match.group(2)
        # Северное или южное полушарие
        if lat_band[0] in 'ABCDEFGHJKLMNOPQRSTUVWXYZ' and lat_band[0] >= 'N':
            return f"EPSG:326{zone:02d}"
        else:
            return f"EPSG:327{zone:02d}"
    
    # Альтернативный поиск: просто цифры зоны
    match = re.search(r'T(\d{2})', filename)
    if match:
        zone = int(match.group(1))
        return f"EPSG:327{zone:02d}"  # По умолчанию южное полушарие
    
    return None

def get_corners_wgs84(filepath):
    """Получить координаты углов изображения в WGS84"""
    try:
        with rasterio.open(filepath) as src:
            height = src.height
            width = src.width
            
            # Координаты углов в системе координат изображения
            corners = [(0, 0), (width, 0), (width, height), (0, height)]
            
            # Преобразуем в географические координаты
            wgs84_corners = []
            for col, row in corners:
                x, y = src.transform * (col, row)
                if src.crs:
                    lon, lat = transform_bounds(src.crs, 'EPSG:4326', x, y, x, y)[:2]
                else:
                    lon, lat = x, y
                wgs84_corners.append((lon, lat))
            
            return wgs84_corners
    except Exception as e:
        app_logger.error(f"Ошибка получения углов: {e}")
        return None

def parse_geotiff_metadata(filepath):
    try:
        with rasterio.open(filepath) as src:
            bounds = src.bounds
            crs = src.crs.to_string() if src.crs else None

            if crs is None:
                guessed = guess_crs_from_filename(filepath)
                if guessed:
                    crs = guessed
                    app_logger.info(f"Угадан CRS для {filepath}: {crs}")
                else:
                    app_logger.warning(f"Не удалось определить CRS для {filepath}")

            width = src.width
            height = src.height
            
            # Добавляем диагностику углов
            corners = get_corners_wgs84(filepath)
            if corners:
                app_logger.info(f"Углы изображения в WGS84: {corners}")
                
                # Вычисляем азимут (угол поворота) между верхним левым и верхним правым углом
                dx = corners[1][0] - corners[0][0]  # разница по долготе
                dy = corners[1][1] - corners[0][1]  # разница по широте
                angle = math.degrees(math.atan2(dy, dx))
                app_logger.info(f"Расчётный угол поворота: {angle} градусов")

            # Получаем трансформацию (аффинное преобразование)
            transform = src.transform
            # Детальный вывод трансформации для отладки
            app_logger.info(f"Transform для {filepath}: a={transform.a}, b={transform.b}, c={transform.c}, d={transform.d}, e={transform.e}, f={transform.f}")
            
            # Проверяем, есть ли поворот
            is_rotated = abs(transform.b) > 1e-6 or abs(transform.d) > 1e-6
            
            if is_rotated:
                angle = math.degrees(math.atan2(transform.b, transform.a))
                app_logger.info(f"Обнаружен поворот {angle} градусов для {filepath}")
            else:
                app_logger.info(f"Поворот не обнаружен для {filepath}")
            
            if crs:
                try:
                    bounds_wgs84 = transform_bounds(crs, 'EPSG:4326', *bounds)
                except Exception as e:
                    app_logger.warning(f"Ошибка преобразования bounds для {filepath}: {e}")
                    bounds_wgs84 = bounds
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
                'transform': transform,
                'is_rotated': is_rotated,
                'transform_params': (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f),
                'min_value': stats['min'] if not np.isnan(stats['min']) else None,
                'max_value': stats['max'] if not np.isnan(stats['max']) else None,
                'mean_value': stats['mean'] if not np.isnan(stats['mean']) else None,
                'stddev': stats['stddev'] if not np.isnan(stats['stddev']) else None
            }
    except Exception as e:
        app_logger.error(f"Не удалось прочитать метаданные {filepath}: {e}", exc_info=True)
        return {
            'bounds': (-180, -90, 180, 90),
            'bounds_wgs84': (-180, -90, 180, 90),
            'crs': None,
            'width': None,
            'height': None,
            'transform': None,
            'is_rotated': False,
            'transform_params': None,
            'min_value': None,
            'max_value': None,
            'mean_value': None,
            'stddev': None
        }