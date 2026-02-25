import urllib.request
import json


def test_api():
    base_url = 'http://127.0.0.1:8000'

    print("Простой тест API")
    print("=" * 50)

    # 1. Тестируем получение дат
    print("1. Тестируем получение дат для TCI:")
    try:
        with urllib.request.urlopen(f'{base_url}/api/available-dates/?product=TCI') as response:
            data = json.loads(response.read().decode())
            dates = data.get('dates', [])
            print(f"   ✅ Успешно! Найдено дат: {len(dates)}")
            for date in dates[:3]:
                print(f"      - {date}")

            # 2. Тестируем получение изображения
            if dates:
                first_date = dates[0]
                print(f"\n2. Тестируем получение изображения для {first_date}:")

                with urllib.request.urlopen(
                        f'{base_url}/api/image-for-date/?date={first_date}&product=TCI') as img_response:
                    img_data = json.loads(img_response.read().decode())

                    if 'preview_url' in img_data:
                        print(f"   ✅ Успешно!")
                        print(f"      URL изображения: {img_data['preview_url']}")
                        print(f"      Тайл: {img_data.get('tile', 'Неизвестно')}")

                        # 3. Проверяем доступность изображения
                        print(f"\n3. Проверяем доступность изображения:")
                        img_url = f"{base_url}{img_data['preview_url']}"
                        try:
                            with urllib.request.urlopen(img_url) as img_check:
                                if img_check.status == 200:
                                    print(f"   ✅ Изображение доступно!")
                                else:
                                    print(f"   ❌ Ошибка: статус {img_check.status}")
                        except Exception as e:
                            print(f"   ❌ Ошибка доступа к изображению: {e}")
                    else:
                        print(f"   ❌ Ошибка: {img_data.get('error', 'Неизвестная ошибка')}")

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")


if __name__ == "__main__":
    test_api()