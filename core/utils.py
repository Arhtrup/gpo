import os
import json
from datetime import datetime
from pathlib import Path
from .models import SatelliteImage


def parse_filename(filename):
    """Парсит имя файла спутникового снимка"""
    try:
        base = os.path.splitext(filename)[0]
        parts = base.split('_')

        if len(parts) < 3:
            return None

        tile = parts[0]
        date_str = parts[1][:8]  # Берем первые 8 символов (YYYYMMDD)
        product = parts[2]

        date_obj = datetime.strptime(date_str, '%Y%m%d').date()
        return tile, date_obj, product
    except Exception as e:
        print(f"Error parsing filename {filename}: {e}")
        return None


def get_available_dates(product_type=None):
    """Получает список доступных дат для продукта"""
    try:
        images = SatelliteImage.objects.all()
        if product_type:
            images = images.filter(product_type=product_type)

        dates = images.values_list('date', flat=True).distinct().order_by('-date')
        return list(dates)
    except Exception as e:
        # Если таблица еще не существует
        print(f"Error getting available dates: {e}")
        return []


def find_image_by_date(date_str, product_type='TC'):
    """
    Быстрый поиск снимка по дате и типу продукта.
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        return SatelliteImage.objects.get(date=date_obj, product_type=product_type)
    except SatelliteImage.DoesNotExist:
        # Пробуем найти ближайшую дату
        images = SatelliteImage.objects.filter(
            product_type=product_type,
            date__lte=date_obj
        ).order_by('-date')

        if images.exists():
            return images.first()
        return None
    except Exception as e:
        print(f"Error finding image: {e}")
        return None


def get_product_stats():
    """Статистика по продуктам"""
    stats = {}
    try:
        for product_type, label in SatelliteImage.PRODUCT_TYPES:
            count = SatelliteImage.objects.filter(product_type=product_type).count()
            dates = SatelliteImage.objects.filter(product_type=product_type) \
                .dates('date', 'year').order_by('-date')
            stats[product_type] = {
                'count': count,
                'years': [d.year for d in dates],
                'label': label
            }
    except Exception as e:
        print(f"Error getting product stats: {e}")

    return stats