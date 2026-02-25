from django.shortcuts import render
from django.http import JsonResponse, FileResponse
from django.conf import settings
from pathlib import Path


def index(request):
    """Главная страница"""
    return render(request, 'core/index.html')


def api_available_dates(request):
    """API: список доступных дат"""
    product_type = request.GET.get('product', 'TCI')

    try:
        data_root = Path(settings.DATA_ROOT)
        preview_dir = data_root / 'Sentinel-2' / 'preview' / product_type

        dates = set()

        if preview_dir.exists():
            # Ищем все JPG файлы
            for ext in ['.jpg', '.JPG']:
                for file_path in preview_dir.rglob(f"*{ext}"):
                    try:
                        filename = file_path.name
                        # Парсим дату из имени файла
                        # Формат: T45VUC_20240610T053649_TCI.jpg
                        parts = filename.split('_')
                        if len(parts) >= 3:
                            date_part = parts[1]  # 20240610T053649
                            date_str = date_part[:8]  # YYYYMMDD
                            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            dates.add(formatted_date)
                    except:
                        continue

        # Сортируем по убыванию (новые сначала)
        sorted_dates = sorted(list(dates), reverse=True)
        return JsonResponse({'dates': sorted_dates})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_image_for_date(request):
    """API: информация о снимке на дату"""
    selected_date = request.GET.get('date')
    product_type = request.GET.get('product', 'TCI')

    if not selected_date:
        return JsonResponse({'error': 'Date parameter is required'}, status=400)

    try:
        data_root = Path(settings.DATA_ROOT)
        date_str = selected_date.replace('-', '')  # 20240610

        # 1. Ищем превью (JPG)
        preview_dir = data_root / 'Sentinel-2' / 'preview' / product_type
        found_preview = None
        tile = None
        original_filename = None

        if preview_dir.exists():
            # Ищем файлы с этой датой
            patterns = [
                f"*{date_str}*{product_type}.jpg",
                f"*{date_str}*{product_type}.JPG",
            ]

            for pattern in patterns:
                matches = list(preview_dir.rglob(pattern))
                if matches:
                    found_preview = matches[0]
                    original_filename = found_preview.stem  # T45VUC_20240610T053649_TCI

                    # Извлекаем тайл
                    parts = original_filename.split('_')
                    if len(parts) >= 1:
                        tile = parts[0]
                    break

        if not found_preview:
            return JsonResponse({'error': 'Preview image not found'}, status=404)

        # 2. Получаем относительный путь для превью
        preview_rel = str(found_preview.relative_to(data_root))
        preview_url = f'/media/{preview_rel}'

        # 3. Ищем файл продукта (TIFF)
        product_dir = data_root / 'Sentinel-2' / product_type
        product_file = None

        if product_dir.exists():
            # Варианты имен файлов продуктов:
            # 1. T45VUC_20240610T053649_TCI.tiff (без _10m)
            # 2. T45VUC_20240610T053649_TCI_10m.tiff (с _10m)

            # Сначала ищем без _10m
            year = date_str[:4]
            search_dirs = [
                product_dir / year,
                product_dir
            ]

            # Варианты имен (сначала без _10m, потом с _10m)
            filename_variants = [
                f"{original_filename}.tiff",
                f"{original_filename}.tif",
                f"{original_filename}_10m.tiff",
                f"{original_filename}_10m.tif",
            ]

            for search_dir in search_dirs:
                if search_dir.exists():
                    for filename in filename_variants:
                        product_path = search_dir / filename
                        if product_path.exists():
                            product_file = product_path
                            break
                    if product_file:
                        break

            # Если не нашли по точному имени, ищем по паттерну
            if not product_file:
                patterns = [
                    f"*{date_str}*{product_type}.tiff",
                    f"*{date_str}*{product_type}.tif",
                    f"*{date_str}*{product_type}*.tiff",
                    f"*{date_str}*{product_type}*.tif",
                ]

                for pattern in patterns:
                    matches = list(product_dir.rglob(pattern))
                    if matches:
                        product_file = matches[0]
                        break

        if product_file:
            product_rel = str(product_file.relative_to(data_root))
            download_url = f'/download-product/?path={product_rel}'
        else:
            download_url = '#'

        return JsonResponse({
            'preview_url': preview_url,
            'download_url': download_url,
            'tile': tile or 'T45VUC',
            'date': selected_date,
            'product_type': product_type
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def download_product(request):
    """Скачивание продукта"""
    file_path = request.GET.get('path')

    if not file_path:
        return JsonResponse({'error': 'File path is required'}, status=400)

    try:
        full_path = Path(settings.DATA_ROOT) / file_path

        if full_path.exists():
            return FileResponse(
                open(full_path, 'rb'),
                as_attachment=True,
                filename=full_path.name
            )
        else:
            return JsonResponse({'error': 'File not found'}, status=404)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)