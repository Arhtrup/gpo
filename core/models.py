from django.db import models

class SatelliteImage(models.Model):
    PRODUCT_TYPES = [
        ('TCI', 'Естественные цвета (True Color)'),
        ('NDVI', 'NDVI'),
        ('NDWI', 'NDWI'),
    ]

    tile = models.CharField(max_length=10)
    date = models.DateField()
    product_type = models.CharField(max_length=10, choices=PRODUCT_TYPES)
    preview_path = models.CharField(max_length=500)
    product_path = models.CharField(max_length=500)

    class Meta:
        unique_together = ['tile', 'date', 'product_type']

    def __str__(self):
        return f"{self.tile}_{self.date}_{self.product_type}"