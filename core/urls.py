from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/available-dates/', views.api_available_dates, name='available_dates'),
    path('api/image-for-date/', views.api_image_for_date, name='image_for_date'),
    path('download-product/', views.download_product, name='download_product'),
]