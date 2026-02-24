from django.core.management.base import BaseCommand
from django.core.cache import cache
from core.utils import get_available_dates


class Command(BaseCommand):
    help = 'Перестраивает кэш доступных дат'

    def handle(self, *args, **options):
        cache.delete('available_dates_all')

        for product_type in ['TC', 'NDVI', 'NDWI']:
            cache_key = f'available_dates_{product_type}'
            dates = get_available_dates(product_type)
            cache.set(cache_key, dates, 3600)  
            self.stdout.write(f"Кэш обновлен для {product_type}: {len(dates)} дат")