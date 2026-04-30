from pydantic import BaseModel
from datetime import date
from typing import Optional, Tuple, List, Any

class SatelliteImageInfo(BaseModel):
    filename: str
    date: date
    layer_type: str
    bounds: Tuple[float, float, float, float]
    bounds_wgs84: Optional[Tuple[float, float, float, float]] = None
    tile_id: str
    crs: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    transform: Optional[Any] = None  # Добавляем трансформацию
    is_rotated: Optional[bool] = False  # Флаг поворота
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    stddev: Optional[float] = None
    histogram: Optional[List[int]] = None