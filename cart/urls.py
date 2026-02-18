
from django.urls import path
from . import views

app_name = "cart"  # ✅ namespace for cart

urlpatterns = [
    path('', views.cart_detail, name='cart_detail'),  # homepage of cart
    path('add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('increase/<int:product_id>/', views.increase_quantity, name='increase_quantity'),
    path('decrease/<int:product_id>/', views.decrease_quantity, name='decrease_quantity'),
]
