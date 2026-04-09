import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "tiff")
DATABASE_PATH = os.path.join(BASE_DIR, "satellite.db")

PRODUCT_SUBDIRS = ['TCI', 'NDVI', 'NDWI']

WEB_TITLE = "Спутниковый просмотрщик"
WEB_DESCRIPTION = "Просмотр спутниковых снимков в реальном времени"

COLOR_BACKGROUND = "linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)"
COLOR_CONTROLS_BG = "rgba(0,0,0,0.7)"
COLOR_BUTTON = "#4caf50"
COLOR_BUTTON_HOVER = "#45a049"
COLOR_SELECT_BG = "rgba(255,255,255,0.9)"
COLOR_SELECT_HOVER = "#fff"
COLOR_TEXT_LIGHT = "#fff"

MAP_HEIGHT = "600px"
MAP_HEIGHT_MOBILE = "400px"
CONTROLS_PADDING = "15px 20px"

DEFAULT_OPACITY = 70  # процент
DEFAULT_MAP_ZOOM = 2
DEFAULT_MAP_CENTER = [0, 0]
MAX_ZOOM_TILES = 12


# НАСТРОЙКИ ТАЙЛОВ
TILE_SIZE = 256  # пикселей
EMPTY_TILE_RGBA = (0, 0, 0, 0)  # прозрачный цвет для пустого тайла


# ПАРАМЕТРЫ БАЗЫ ДАННЫХ
DB_INIT_TABLE = True  # автоматически создавать таблицу при старте


# ПАРАМЕТРЫ СЕРВЕРА
HOST = "0.0.0.0"
PORT = 8000

# НАСТРОЙКИ СРАВНЕНИЯ
ENABLE_COMPARE = True
STATISTICS_TAGS = {
    'min': 'STATISTICS_MINIMUM',
    'max': 'STATISTICS_MAXIMUM',
    'mean': 'STATISTICS_MEAN',
    'stddev': 'STATISTICS_STDDEV',
    'valid_percent': 'STATISTICS_VALID_PERCENT'
}