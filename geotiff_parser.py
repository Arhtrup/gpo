import rasterio
import numpy as np

def parse_geotiff_metadata(filepath):
    """
    Извлекает полную информацию из GeoTIFF.
    
    Возвращает словарь с ключами:
        bounds: (left, bottom, right, top) в географических координатах
        crs: строка с кодом системы координат (например, 'EPSG:4326')
        width: ширина в пикселях
        height: высота в пикселях
        min_value: минимальное значение (по первому каналу)
        max_value: максимальное значение
        mean_value: среднее значение
        stddev: стандартное отклонение
    """
    with rasterio.open(filepath) as src:
        # Границы
        bounds = src.bounds  # (left, bottom, right, top)
        
        # Система координат
        crs = src.crs.to_string() if src.crs else None
        
        # Размеры
        width = src.width
        height = src.height
        
        # Статистика (сначала пробуем теги, иначе вычисляем)
        tags = src.tags()
        stats = {}
        try:
            stats['min'] = float(tags.get('STATISTICS_MINIMUM', np.nan))
            stats['max'] = float(tags.get('STATISTICS_MAXIMUM', np.nan))
            stats['mean'] = float(tags.get('STATISTICS_MEAN', np.nan))
            stats['stddev'] = float(tags.get('STATISTICS_STDDEV', np.nan))
        except (ValueError, TypeError):
            stats = {'min': np.nan, 'max': np.nan, 'mean': np.nan, 'stddev': np.nan}
        
        # Если статистика не найдена в тегах, вычисляем по первому каналу
        if np.isnan(stats['min']):
            data = src.read(1)
            # Игнорируем NoData (NaN)
            data = data[~np.isnan(data)]
            if data.size > 0:
                stats['min'] = float(data.min())
                stats['max'] = float(data.max())
                stats['mean'] = float(data.mean())
                stats['stddev'] = float(data.std())
        
        return {
            'bounds': bounds,
            'crs': crs,
            'width': width,
            'height': height,
            'min_value': stats['min'] if not np.isnan(stats['min']) else None,
            'max_value': stats['max'] if not np.isnan(stats['max']) else None,
            'mean_value': stats['mean'] if not np.isnan(stats['mean']) else None,
            'stddev': stats['stddev'] if not np.isnan(stats['stddev']) else None
        }