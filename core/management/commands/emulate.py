import shutil
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Эмуляция создания разницы между двумя снимками'

    def handle(self, *args, **options):
        # Эмулируем работу скрипта: копируем первый файл как результат
        source_preview = 'path/to/first_preview.jpg'
        target_preview = 'path/to/diff_preview.jpg'
        shutil.copy(source_preview, target_preview)
        self.stdout.write('Разница создана (эмуляция)')