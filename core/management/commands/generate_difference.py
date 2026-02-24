import os
import shutil
from django.conf import settings


def generate_difference(date1, date2, product_type):
    """
    Эмуляция создания разницы между двумя снимками.
    В реальности здесь должен быть вызов вашего алгоритма.
    """

    # Находим исходные файлы
    from core.models import SatelliteImage

    try:
        image1 = SatelliteImage.objects.get(date=date1, product_type=product_type)
        image2 = SatelliteImage.objects.get(date=date2, product_type=product_type)

        # Создаем директорию для результатов разницы
        diff_dir = os.path.join(settings.MEDIA_ROOT, 'diff_results')
        os.makedirs(diff_dir, exist_ok=True)

        # Имена результирующих файлов
        diff_preview_name = f"{date1}_{date2}_{product_type}.jpg"
        diff_product_name = f"{date1}_{date2}_{product_type}.tiff"

        diff_preview_path = os.path.join(diff_dir, diff_preview_name)
        diff_product_path = os.path.join(diff_dir, diff_product_name)

        # Эмуляция: копируем первый файл как результат
        source_preview = os.path.join(settings.DATA_ROOT, image1.preview_path)
        source_product = os.path.join(settings.DATA_ROOT, image1.product_path)

        if os.path.exists(source_preview):
            shutil.copy(source_preview, diff_preview_path)

        if os.path.exists(source_product):
            shutil.copy(source_product, diff_product_path)

        return {
            'preview_path': os.path.relpath(diff_preview_path, settings.DATA_ROOT),
            'product_path': os.path.relpath(diff_product_path, settings.DATA_ROOT),
            'status': 'success'
        }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}