import rasterio
from rasterio.transform import Affine

def get_geocoordinates_from_tiff(tiff_path):
    """
    Извлекает географические координаты из GeoTIFF файла.
    
    Параметры:
        tiff_path (str): путь к TIFF-файлу
        
    Возвращает:
        dict: словарь с информацией о привязке, границах и системе координат
    """
    with rasterio.open(tiff_path) as src:
        # Проверяем наличие геопривязки
        if src.transform.is_identity:
            return {"error": "Файл не содержит геопривязки (не GeoTIFF или отсутствует трансформация)."}
        
        # Границы изображения в координатах проекции
        bounds = src.bounds
        left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
        
        # Система координат
        crs = src.crs
        crs_string = crs.to_string() if crs else "Не определена"
        
        # Трансформационная матрица (привязка)
        transform = src.transform
        
        # Размеры изображения
        width, height = src.width, src.height
        
        # Центр изображения
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        
        return {
            'bounds': {'left': left, 'bottom': bottom, 'right': right, 'top': top},
            'crs': crs_string,
            'transform': transform,
            'size': (width, height),
            'center': (center_x, center_y)
        }

def pixel_to_geo(tiff_path, row, col):
    """
    Преобразует координаты пикселя (строка, столбец) в географические координаты.
    
    Параметры:
        tiff_path (str): путь к TIFF-файлу
        row (int): номер строки (Y)
        col (int): номер столбца (X)
        
    Возвращает:
        tuple: (x, y) географические координаты
    """
    with rasterio.open(tiff_path) as src:
        x, y = src.transform * (col, row)
        return x, y

def geo_to_pixel(tiff_path, x, y):
    """
    Преобразует географические координаты в координаты пикселя (строка, столбец).
    
    Параметры:
        tiff_path (str): путь к TIFF-файлу
        x (float): географическая координата X (долгота / восток)
        y (float): географическая координата Y (широта / север)
        
    Возвращает:
        tuple: (row, col) координаты пикселя
    """
    with rasterio.open(tiff_path) as src:
        col, row = ~src.transform * (x, y)
        return int(row), int(col)

# Пример использования
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 2:
        print("Использование: python script.py путь_к_файлу.tif")
        sys.exit(1)
    
    tiff_file = sys.argv[1]
    try:
        info = get_geocoordinates_from_tiff(tiff_file)
        if 'error' in info:
            print(info['error'])
        else:
            print("=== Информация о GeoTIFF ===")
            print(f"Границы (minx, miny, maxx, maxy): {info['bounds']['left']:.6f}, {info['bounds']['bottom']:.6f}, "
                  f"{info['bounds']['right']:.6f}, {info['bounds']['top']:.6f}")
            print(f"Система координат: {info['crs']}")
            print(f"Размер: {info['size'][0]} x {info['size'][1]} пикселей")
            print(f"Центр: ({info['center'][0]:.6f}, {info['center'][1]:.6f})")
            
            # Демонстрация преобразования для центрального пикселя
            col = info['size'][0] // 2
            row = info['size'][1] // 2
            x, y = pixel_to_geo(tiff_file, row, col)
            print(f"\nКоординаты центрального пикселя ({row}, {col}): ({x:.6f}, {y:.6f})")
            
    except Exception as e:
        print(f"Ошибка: {e}")