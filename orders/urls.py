from django.urls import path
from . import views

app_name = "orders"   # VERY IMPORTANT


urlpatterns = [
    path('create-checkout/', views.create_checkout_session, name='stripe_checkout'),
    path('success/', views.order_success, name='order_success'),
    path('webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('track-order/', views.order_lookup, name='track_order'),
]
