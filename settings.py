import os
LOG_LEVEL = "DEBUG"
# ------------------- БАЗОВЫЕ ПУТИ -------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "tiff")           # папка со снимками
DATABASE_PATH = os.path.join(BASE_DIR, "satellite.db") # файл БД
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")   # папка с шаблонами

# ------------------- ТИПЫ ПРОДУКТОВ -------------------
# Подпапки внутри IMAGES_DIR, соответствующие типам слоёв
PRODUCT_SUBDIRS = ['TCI', 'NDVI', 'NDWI']

# ------------------- ПАРАМЕТРЫ ТАЙЛОВ -------------------
TILE_SIZE = 256                      # размер тайла в пикселях
MAX_ZOOM_TILES = 12                  # максимальный зум для генерации тайлов из GeoTIFF
EMPTY_TILE_RGBA = (0, 0, 0, 0)       # цвет пустого тайла (прозрачный)

# ------------------- НАСТРОЙКИ ПОДЛОЖКИ (TILE LAYER) -------------------
DEFAULT_BASE_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_BASE_ATTRIBUTION = "© OpenStreetMap contributors"
DEFAULT_BASE_MAX_ZOOM = 19

# ------------------- ПАРАМЕТРЫ КАРТЫ -------------------
DEFAULT_MAP_ZOOM = 2
DEFAULT_MAP_CENTER = [0, 0]           # широта, долгота
DEFAULT_OPACITY = 70                  # начальная прозрачность спутникового слоя (%)

# ------------------- ВНЕШНИЙ ВИД (CSS) -------------------
WEB_TITLE = "Спутниковый просмотрщик"
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

# ------------------- БАЗА ДАННЫХ -------------------
DB_INIT_TABLE = True                 # автоматически создавать таблицу при старте

# ------------------- СЕРВЕР -------------------
HOST = "0.0.0.0"
PORT = 8000

# ------------------- СРАВНЕНИЕ СЛОЁВ -------------------
ENABLE_COMPARE = True                # показывать панель сравнения
# Теги статистики, которые ищем в GeoTIFF
STATISTICS_TAGS = {
    'min': 'STATISTICS_MINIMUM',
    'max': 'STATISTICS_MAXIMUM',
    'mean': 'STATISTICS_MEAN',
    'stddev': 'STATISTICS_STDDEV',
    'valid_percent': 'STATISTICS_VALID_PERCENT'
}

# ------------------- ЛОГИРОВАНИЕ -------------------
LOG_FILE = os.path.join(BASE_DIR, "logs", "satellite_viewer.log")
LOG_LEVEL = "INFO"                     # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_MAX_BYTES = 10 * 1024 * 1024       # 10 MB
LOG_BACKUP_COUNT = 5                   # количество ротируемых файлов

# Создаём папку для логов, если её нет
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ------------------- ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ -------------------
# Разрешить ли CORS (для разработки)
CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]