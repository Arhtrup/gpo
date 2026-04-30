import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "tiff")
DATABASE_PATH = os.path.join(BASE_DIR, "satellite.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

PRODUCT_SUBDIRS = ['TCI', 'NDVI', 'NDWI']

MAX_IMAGE_WIDTH = 2048
MAX_IMAGE_HEIGHT = 2048
IMAGE_QUALITY = 85
REPROJECT_RESAMPLING = "bilinear"
WGS84_EPSG = "EPSG:4326"

DEFAULT_BASE_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_BASE_ATTRIBUTION = "© OpenStreetMap contributors"
DEFAULT_BASE_MAX_ZOOM = 19

DEFAULT_MAP_ZOOM = 2
DEFAULT_MAP_CENTER = [0, 0]
DEFAULT_OPACITY = 70

WEB_TITLE = "Спутниковый просмотрщик (с выпрямлением)"
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

LAYER_LABELS = {
    "TCI": "True Color Image",
    "NDVI": "Normalized Difference Vegetation Index",
    "NDWI": "Normalized Difference Water Index"
}

ENABLE_COMPARE = True
COMPARE_SHOW_HISTOGRAMS = True
COMPARE_HISTOGRAM_BINS = 50
COMPARE_AREA_SIZE = (256, 256)

DB_INIT_TABLE = True

HOST = "0.0.0.0"
PORT = 8000

LOG_FILE = os.path.join(BASE_DIR, "logs", "satellite_viewer.log")
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]