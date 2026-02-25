from django.core.management.base import BaseCommand
from pathlib import Path
from django.conf import settings
from core.models import SatelliteImage


class Command(BaseCommand):
    help = 'Проверяет целостность данных (наличие файлов)'

    def handle(self, *args, **options):
        missing_previews = 0
        missing_products = 0

        for image in SatelliteImage.objects.all():
            preview = Path(settings.DATA_ROOT) / image.preview_path
            product = Path(settings.DATA_ROOT) / image.product_path

            if not preview.exists():
                self.stdout.write(f"❌ Превью отсутствует: {image}")
                missing_previews += 1

            if not product.exists():
                self.stdout.write(f"❌ Продукт отсутствует: {image}")
                missing_products += 1

        total = SatelliteImage.objects.count()
        self.stdout.write(f"\nСтатистика проверки:")
        self.stdout.write(f"Всего записей: {total}")
        self.stdout.write(f"Отсутствует превью: {missing_previews}")
        self.stdout.write(f"Отсутствует продуктов: {missing_products}")