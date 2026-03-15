from django.contrib import admin

# Register your models here.

from .models import ShippingRate

@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ['country', 'country_code', 'standard_price', 'tracked_price', 'is_active']
    search_fields = ['country', 'country_code']
