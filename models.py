from pydantic import BaseModel
from datetime import date
from typing import List, Tuple

class SatelliteImageInfo(BaseModel):
    filename: str
    date: date
    layer_type: str   # TCI, NDVI, NDWI
    bounds: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)
    tile_id: str       # T45VUC и т.п.