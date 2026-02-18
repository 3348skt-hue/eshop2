from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<int:id>/', views.product_detail, name='product_detail'),
    path('products/', views.products_page, name='products_page'),
    path('categories/', views.categories_page, name='categories_page'),
]
