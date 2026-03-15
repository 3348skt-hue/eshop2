from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<int:id>/', views.product_detail, name='product_detail'),
    path('products/', views.products_page, name='products_page'),
    path('categories/', views.categories_page, name='categories_page'),
    path('contact/', views.contact_page, name='contact_page'),
    path('shipping/', views.shipping_page, name='shipping_page'),
    path('returns/', views.returns_page, name='returns_page'),
]
