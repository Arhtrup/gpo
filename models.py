from pydantic import BaseModel
from datetime import date
from typing import Optional, Tuple

class SatelliteImageInfo(BaseModel):
    filename: str
    date: date
    layer_type: str          # TCI, NDVI, NDWI
    bounds: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)
    tile_id: str
    crs: Optional[str] = None          # строка EPSG или WKT
    width: Optional[int] = None        # ширина в пикселях
    height: Optional[int] = None       # высота в пикселях
    min_value: Optional[float] = None  # статистика минимума
    max_value: Optional[float] = None  # статистика максимума
    mean_value: Optional[float] = None # среднее
    stddev: Optional[float] = None     # стандартное отклонение