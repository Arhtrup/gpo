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
    """HTML-страница с картой и UI для выбора дат и типа отображения"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Satellite Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body { margin:0; padding:0; font-family: Arial, sans-serif; }
            #map { height:100vh; width:100vw; }
            #controls {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 1000;
                background: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                min-width: 200px;
            }
            .control-group {
                margin-bottom: 15px;
            }
            .control-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
                color: #333;
            }
            select {
                width: 100%;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
            .layer-item {
                display: flex;
                align-items: center;
                margin-bottom: 8px;
                padding: 5px;
                background: #f5f5f5;
                border-radius: 4px;
            }
            .layer-item input[type="checkbox"] {
                margin-right: 8px;
            }
            .layer-item label {
                margin: 0;
                font-weight: normal;
                cursor: pointer;
                flex-grow: 1;
            }
            .layer-item input[type="range"] {
                width: 60px;
                margin-left: 5px;
            }
            .opacity-value {
                font-size: 12px;
                color: #666;
                margin-left: 5px;
                min-width: 35px;
            }
            h3 {
                margin: 0 0 10px 0;
                color: #333;
                font-size: 16px;
            }
            .date-selector {
                margin-bottom: 15px;
            }
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div id="controls">
            <h3>Управление слоями</h3>
            <div class="control-group">
                <label for="dateSelect">Дата:</label>
                <select id="dateSelect" onchange="onDateChange()">
                    <option value="">Загрузка...</option>
                </select>
            </div>
            <div id="layersContainer">
                <p>Выберите дату для загрузки слоёв</p>
            </div>
        </div>

        <script>
            const map = L.map('map').setView([55.75, 37.62], 10);
            
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap'
            }).addTo(map);

            // Хранилище для активных слоёв
            const activeLayers = {};

            // Загрузка доступных дат
            fetch('/api/dates')
                .then(r => r.json())
                .then(dates => {
                    const select = document.getElementById('dateSelect');
                    select.innerHTML = '';
                    
                    if (dates.length === 0) {
                        select.innerHTML = '<option value="">Нет доступных дат</option>';
                        return;
                    }
                    
                    dates.forEach(date => {
                        const option = document.createElement('option');
                        option.value = date;
                        option.textContent = date;
                        select.appendChild(option);
                    });
                    
                    // Загружаем слои для первой даты
                    if (dates.length > 0) {
                        loadLayersForDate(dates[0]);
                    }
                });

            function onDateChange() {
                const date = document.getElementById('dateSelect').value;
                if (date) {
                    loadLayersForDate(date);
                }
            }

            function loadLayersForDate(date) {
                fetch(`/api/layers/${date}`)
                    .then(r => r.json())
                    .then(layers => {
                        const container = document.getElementById('layersContainer');
                        
                        if (layers.length === 0) {
                            container.innerHTML = '<p>Нет слоёв для выбранной даты</p>';
                            return;
                        }
                        
                        let html = '<div class="control-group"><label>Доступные слои:</label>';
                        
                        layers.forEach(layer => {
                            const layerId = `layer_${date}_${layer.layer}`;
                            const isActive = activeLayers[layerId] ? true : false;
                            
                            html += `
                                <div class="layer-item">
                                    <input type="checkbox" 
                                           id="${layerId}" 
                                           ${isActive ? 'checked' : ''} 
                                           onchange="toggleLayer('${date}', '${layer.layer}', this.checked)">
                                    <label for="${layerId}">${layer.layer}</label>
                                    <input type="range" 
                                           id="opacity_${layerId}" 
                                           min="0" 
                                           max="1" 
                                           step="0.1" 
                                           value="${activeLayers[layerId]?.opacity || 0.7}"
                                           onchange="updateOpacity('${date}', '${layer.layer}', this.value)"
                                           oninput="updateOpacityLabel('${layerId}', this.value)">
                                    <span class="opacity-value" id="opacityVal_${layerId}">${activeLayers[layerId]?.opacity || 0.7}</span>
                                </div>
                            `;
                        });
                        
                        html += '</div>';
                        container.innerHTML = html;
                        
                        // Автоматически включаем слои, которые были активны
                        layers.forEach(layer => {
                            const layerId = `layer_${date}_${layer.layer}`;
                            if (activeLayers[layerId]) {
                                addLayerToMap(date, layer.layer, activeLayers[layerId].opacity);
                            }
                        });
                    });
            }

            function toggleLayer(date, layerType, isChecked) {
                const layerId = `layer_${date}_${layerType}`;
                
                if (isChecked) {
                    const opacityInput = document.getElementById(`opacity_${layerId}`);
                    const opacity = opacityInput ? parseFloat(opacityInput.value) : 0.7;
                    addLayerToMap(date, layerType, opacity);
                } else {
                    if (activeLayers[layerId]) {
                        map.removeLayer(activeLayers[layerId].layer);
                        delete activeLayers[layerId];
                    }
                }
            }

            function addLayerToMap(date, layerType, opacity) {
                const layerId = `layer_${date}_${layerType}`;
                
                // Удаляем существующий слой если есть
                if (activeLayers[layerId]) {
                    map.removeLayer(activeLayers[layerId].layer);
                }
                
                // Создаём новый слой
                const tileLayer = L.tileLayer(`/tiles/${date}/${layerType}/{z}/{x}/{y}.png`, {
                    attribution: 'Satellite',
                    opacity: opacity
                }).addTo(map);
                
                activeLayers[layerId] = {
                    layer: tileLayer,
                    opacity: opacity
                };
            }

            function updateOpacity(date, layerType, value) {
                const layerId = `layer_${date}_${layerType}`;
                const opacity = parseFloat(value);
                
                if (activeLayers[layerId]) {
                    activeLayers[layerId].layer.setOpacity(opacity);
                    activeLayers[layerId].opacity = opacity;
                }
            }

            function updateOpacityLabel(layerId, value) {
                document.getElementById(`opacityVal_${layerId}`).textContent = parseFloat(value).toFixed(1);
            }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)