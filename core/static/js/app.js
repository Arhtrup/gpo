document.addEventListener('DOMContentLoaded', function() {
    // Инициализация слайдера года
    const yearSlider = document.getElementById('year-slider');
    const currentYearSpan = document.getElementById('current-year');

    yearSlider.addEventListener('input', function() {
        currentYearSpan.textContent = this.value;
        loadDatesForYear(this.value);
    });

    // Обработчики кнопок продуктов
    document.querySelectorAll('.product-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.product-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const productType = this.dataset.product;
            loadAvailableDates(productType);
        });
    });

    // Форма сравнения
    document.getElementById('difference-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const date1 = document.getElementById('date1-select').value;
        const date2 = document.getElementById('date2-select').value;
        const product = document.getElementById('diff-product-select').value;

        if (date1 && date2) {
            calculateDifference(date1, date2, product);
        }
    });

    // Загрузка начальных данных
    loadAvailableDates('TC');
});

async function loadAvailableDates(productType) {
    try {
        const response = await fetch(`/api/available-dates/?product=${productType}`);
        const data = await response.json();

        if (data.dates && data.dates.length > 0) {
            updateDateButtons(data.dates, productType);

            // Автоматически выбираем последнюю дату
            loadImageForDate(data.dates[0], productType);
        }
    } catch (error) {
        console.error('Error loading dates:', error);
    }
}

async function loadImageForDate(dateStr, productType) {
    try {
        const response = await fetch(`/api/image-for-date/?date=${dateStr}&product=${productType}`);
        const data = await response.json();

        if (!data.error) {
            // Обновляем превью
            document.getElementById('preview-image').src = data.preview_url;
            document.getElementById('image-tile').textContent = data.tile;
            document.getElementById('image-date').textContent = data.date;
            document.getElementById('download-btn').href = data.download_url;
        }
    } catch (error) {
        console.error('Error loading image:', error);
    }
}