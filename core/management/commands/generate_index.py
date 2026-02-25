import os
import json
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import SatelliteImage
from core.utils import parse_filename
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Сканирует директории с превью и продуктами, создает записи в базе данных и индекс-файлы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Перезаписать существующие записи в базе данных'
        )
        parser.add_argument(
            '--skip-index-files',
            action='store_true',
            help='Не создавать текстовые индекс-файлы'
        )
        parser.add_argument(
            '--product',
            type=str,
            help='Обработать только указанный тип продукта (TCI, NDVI, NDWI)'
        )
        parser.add_argument(
            '--data-dir',
            type=str,
            default=None,
            help='Путь к директории с данными (по умолчанию settings.DATA_ROOT)'
        )

    def handle(self, *args, **options):
        force_update = options['force']
        skip_index_files = options['skip_index_files']
        target_product = options['product']
        data_dir = options['data_dir'] or getattr(settings, 'DATA_ROOT', '/data')

        # Определяем структуру директорий
        base_path = Path(data_dir) / 'Sentinel-2'

        if not base_path.exists():
            self.stdout.write(self.style.ERROR(f"Директория не найдена: {base_path}"))
            self.stdout.write(f"Проверьте, существует ли директория: {base_path}")
            return

        # Соответствие директорий и типов продуктов
        product_configs = {
            'TCI': {
                'preview_dir': base_path / 'preview' / 'TCI',
                'product_dir': base_path / 'TCI',
                'preview_ext': ['.jpg', '.JPG', '.jpeg', '.JPEG'],
                'product_ext': ['.tiff', '.tif', '.TIFF', '.TIF']  # Все продукты в .tiff
            },
            'NDVI': {
                'preview_dir': base_path / 'preview' / 'NDVI',
                'product_dir': base_path / 'NDVI',
                'preview_ext': ['.jpg', '.JPG', '.jpeg', '.JPEG'],
                'product_ext': ['.tiff', '.tif', '.TIFF', '.TIF']  # Все продукты в .tiff
            },
            'NDWI': {
                'preview_dir': base_path / 'preview' / 'NDWI',
                'product_dir': base_path / 'NDWI',
                'preview_ext': ['.jpg', '.JPG', '.jpeg', '.JPEG'],
                'product_ext': ['.tiff', '.tif', '.TIFF', '.TIF']  # Все продукты в .tiff
            }
        }

        # Фильтруем продукты, если указан конкретный
        if target_product:
            if target_product not in product_configs:
                self.stdout.write(self.style.ERROR(f'Неизвестный тип продукта: {target_product}'))
                return
            products_to_process = {target_product: product_configs[target_product]}
        else:
            products_to_process = product_configs

        total_processed = 0

        for product_type, config in products_to_process.items():
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(f"📂 Обработка продукта: {product_type}")
            self.stdout.write(f"📁 Директория превью: {config['preview_dir']}")
            self.stdout.write(f"📁 Директория продуктов: {config['product_dir']}")

            # Сканируем директорию превью
            preview_dir = config['preview_dir']
            if not preview_dir.exists():
                self.stdout.write(f"  ⚠️ Директория превью не найдена: {preview_dir}")
                continue

            # Собираем все файлы превью (рекурсивно по годам)
            preview_files = []
            for ext in config['preview_ext']:
                # Ищем во всех поддиректориях (включая годовые)
                preview_files.extend(list(preview_dir.rglob(f"*{ext}")))
                preview_files.extend(list(preview_dir.rglob(f"*{ext.upper()}")))
                preview_files.extend(list(preview_dir.rglob(f"*{ext.lower()}")))

            self.stdout.write(f"  📊 Найдено файлов превью: {len(preview_files)}")

            processed_for_product = 0

            for preview_file in preview_files:
                try:
                    # Парсим имя файла
                    filename = preview_file.name

                    # Формат: T45VUC_20250602T052649_TCI.jpg
                    base_name = preview_file.stem  # Без расширения
                    parts = base_name.split('_')

                    if len(parts) < 3:
                        self.stdout.write(f"  ⚠️ Неверный формат имени файла (мало частей): {filename}")
                        continue

                    tile = parts[0]
                    date_time_str = parts[1]  # Полная строка с временем: 20250602T052649

                    # Извлекаем дату (первые 8 символов)
                    if len(date_time_str) < 8:
                        self.stdout.write(f"  ⚠️ Неверный формат даты: {date_time_str}")
                        continue

                    date_str = date_time_str[:8]  # YYYYMMDD
                    file_product_type = parts[2]

                    # Проверяем тип продукта
                    if file_product_type.upper() != product_type.upper():
                        self.stdout.write(
                            f"  ⚠️ Тип продукта не совпадает: {file_product_type} != {product_type} (файл: {filename})")
                        continue

                    try:
                        date_obj = datetime.strptime(date_str, '%Y%m%d').date()
                    except ValueError:
                        self.stdout.write(f"  ⚠️ Неверный формат даты: {date_str}")
                        continue

                    # Формируем относительные пути
                    try:
                        # Пытаемся получить путь относительно data_dir
                        preview_rel_path = str(preview_file.relative_to(Path(data_dir)))
                    except ValueError:
                        # Если файл не в data_dir, используем абсолютный путь
                        preview_rel_path = str(preview_file)

                    # Ищем соответствующий файл продукта
                    year = date_obj.strftime('%Y')

                    # Варианты поиска файла продукта
                    product_found = False
                    product_file = None
                    product_rel_path = None

                    # 1. Ищем в директории по году
                    product_year_dir = config['product_dir'] / year
                    if product_year_dir.exists():
                        # Ищем файлы с похожим именем
                        search_patterns = [
                            f"{tile}_{date_time_str}_{product_type}*",
                            f"{tile}_{date_str}*{product_type}*",
                            f"{tile}*{date_str}*{product_type}*"
                        ]

                        for pattern in search_patterns:
                            for ext in config['product_ext']:
                                matches = list(product_year_dir.glob(f"{pattern}{ext}"))
                                matches.extend(list(product_year_dir.glob(f"{pattern}{ext.upper()}")))
                                matches.extend(list(product_year_dir.glob(f"{pattern}{ext.lower()}")))

                                if matches:
                                    product_file = matches[0]
                                    product_found = True
                                    break
                            if product_found:
                                break

                    # 2. Ищем в основной директории продукта
                    if not product_found:
                        search_patterns = [
                            f"{tile}_{date_time_str}_{product_type}*",
                            f"{tile}_{date_str}*{product_type}*"
                        ]

                        for pattern in search_patterns:
                            for ext in config['product_ext']:
                                matches = list(config['product_dir'].glob(f"{pattern}{ext}"))
                                matches.extend(list(config['product_dir'].glob(f"{pattern}{ext.upper()}")))
                                matches.extend(list(config['product_dir'].glob(f"{pattern}{ext.lower()}")))

                                if matches:
                                    product_file = matches[0]
                                    product_found = True
                                    break
                            if product_found:
                                break

                    # 3. Ищем рекурсивно
                    if not product_found:
                        search_patterns = [
                            f"*{tile}_{date_time_str}_{product_type}*",
                            f"*{tile}_{date_str}*{product_type}*",
                            f"*{date_str}*{product_type}*"
                        ]

                        for pattern in search_patterns:
                            for ext in config['product_ext']:
                                matches = list(config['product_dir'].rglob(f"{pattern}{ext}"))
                                if matches:
                                    product_file = matches[0]
                                    product_found = True
                                    break
                            if product_found:
                                break

                    if product_found and product_file:
                        try:
                            product_rel_path = str(product_file.relative_to(Path(data_dir)))
                        except ValueError:
                            product_rel_path = str(product_file)
                    else:
                        self.stdout.write(f"  ⚠️ Файл продукта не найден для: {filename}")
                        product_rel_path = "NOT_FOUND"

                    # Создаем или обновляем запись в базе данных
                    defaults = {
                        'preview_path': preview_rel_path,
                        'product_path': product_rel_path
                    }

                    try:
                        obj, created = SatelliteImage.objects.update_or_create(
                            tile=tile,
                            date=date_obj,
                            product_type=product_type,
                            defaults=defaults
                        )

                        if created:
                            self.stdout.write(f"    ✅ Создана запись: {obj}")
                            processed_for_product += 1
                        elif force_update:
                            obj.preview_path = preview_rel_path
                            obj.product_path = product_rel_path
                            obj.save()
                            self.stdout.write(f"    🔄 Обновлена запись: {obj}")
                            processed_for_product += 1
                        else:
                            self.stdout.write(f"    ⏭️  Уже существует: {obj}")

                        total_processed += 1

                    except Exception as db_error:
                        self.stdout.write(f"    ❌ Ошибка БД: {db_error}")
                        continue

                except Exception as e:
                    self.stdout.write(f"    ❌ Ошибка обработки файла {filename}: {str(e)}")
                    continue

            self.stdout.write(f"  📈 Обработано для {product_type}: {processed_for_product} файлов")

            # Создаем текстовые индекс-файлы (опционально)
            if not skip_index_files and processed_for_product > 0:
                self._create_index_files(product_type, data_dir)

        # Сводная статистика
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS(f"🎉 Обработка завершена! Всего обработано файлов: {total_processed}"))

        # Выводим статистику по продуктам
        try:
            for product_type in product_configs.keys():
                count = SatelliteImage.objects.filter(product_type=product_type).count()
                self.stdout.write(f"  📊 {product_type}: {count} записей в базе")
        except Exception as e:
            self.stdout.write(f"  ❌ Ошибка получения статистики: {e}")

    def _create_index_files(self, product_type, data_dir):
        """Создает текстовые и JSON индекс-файлы"""
        try:
            index_dir = Path(data_dir) / 'index_files'
            index_dir.mkdir(exist_ok=True)

            # Получаем все файлы для данного типа продукта из базы
            images = SatelliteImage.objects.filter(product_type=product_type).order_by('-date')

            # TXT файл (простой список путей)
            txt_file = index_dir / f'preview_{product_type}.txt'
            with open(txt_file, 'w', encoding='utf-8') as f:
                for image in images:
                    f.write(f"{image.preview_path}\n")

            # JSON файл
            json_file = index_dir / f'preview_{product_type}.json'
            json_data = []
            for image in images:
                json_data.append({
                    'tile': image.tile,
                    'date': image.date.strftime('%Y-%m-%d'),
                    'preview_path': image.preview_path,
                    'product_path': image.product_path,
                    'product_type': image.product_type
                })

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            self.stdout.write(f"  📁 Созданы индекс-файлы для {product_type}:")
            self.stdout.write(f"    - {txt_file}")
            self.stdout.write(f"    - {json_file}")
        except Exception as e:
            self.stdout.write(f"  ❌ Ошибка создания индекс-файлов: {e}")