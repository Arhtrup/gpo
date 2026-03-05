from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
import os
from datetime import datetime
import json
import rasterio
import io
import database
import tile_utils
from settings import IMAGES_DIR
from models import SatelliteImageInfo

database.init_db()

if not database.get_all_dates():
    for fname in os.listdir(IMAGES_DIR):
        if fname.endswith(".jpg"):
            parts = fname.replace(".jpg", "").split("_")
            if len(parts) == 3:
                tile_id, datetime_str, layer = parts
                date_str = datetime_str.split("T")[0]
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d").date()
                except:
                    continue
                filepath = os.path.join(IMAGES_DIR, fname)
                try:
                    with rasterio.open(filepath) as src:
                        bounds = src.bounds 
                except Exception as e:
                    print(f"Warning: Could not read georeferencing for {fname}: {e}")
                    bounds = (-180, -90, 180, 90)
                
                info = SatelliteImageInfo(
                    filename=fname,
                    date=dt,
                    layer_type=layer,
                    bounds=bounds,
                    tile_id=tile_id
                )
                database.add_image(info)
                print(f"Added {fname} to database.")
app = FastAPI(title="Satellite Image Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dates", response_model=list[str])
async def get_dates():
    """Список всех доступных дат в формате YYYY-MM-DD"""
    return database.get_all_dates()

@app.get("/api/layers/{date}")
async def get_layers(date: str):
    """Список доступных слоёв для указанной даты"""
    layers = database.get_layers_for_date(date)
    return layers

@app.get("/tiles/{date}/{layer}/{z}/{x}/{y}.png")
async def tile(date: str, layer: str, z: int, x: int, y: int):
    """Отдача тайла для конкретной даты и слоя"""
    img_info = database.get_image_by_layer_and_date(date, layer)
    if not img_info:
        raise HTTPException(status_code=404, detail="Layer not found for this date")

    tile_data = await tile_utils.get_tile(img_info["filename"], z, x, y)
    if tile_data is None:
        from PIL import Image
        empty = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        img_bytes = io.BytesIO()
        empty.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return StreamingResponse(img_bytes, media_type="image/png")

    return StreamingResponse(tile_data, media_type="image/png")

@app.get("/", response_class=HTMLResponse)
async def get_map():
    """Минимальная HTML-страница с картой для тестирования (не относится к заданию, но удобно)"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Satellite Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style> body { margin:0; padding:0; } #map { height:100vh; width:100vw; } </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            const map = L.map('map').setView([0, 0], 2);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap'
            }).addTo(map);

            fetch('/api/dates')
                .then(r => r.json())
                .then(dates => {
                    if (dates.length > 0) {
                        const date = dates[0];

                        fetch(`/api/layers/${date}`)
                            .then(r => r.json())
                            .then(layers => {
                                layers.forEach(l => {

                                    L.tileLayer(`/tiles/${date}/${l.layer}/{z}/{x}/{y}.png`, {
                                        attribution: 'Satellite',
                                        opacity: 0.7
                                    }).addTo(map);
                                });
                            });
                    }
                });
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)