from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Store, Category, SubCategory


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'price', 'stock', 'image_preview']
    list_filter = ['category', 'subcategory', 'store']
    search_fields = ['name', 'sku']
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        if obj.image:
            url = str(obj.image)
            if not url.startswith('http'):
                url = '/media/' + url
            return format_html(
                '<img src="{}" style="height:60px; width:60px; object-fit:cover; border-radius:4px;" />',
                url
            )
        return '—'
    image_preview.short_description = 'Image'


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category']
    list_filter = ['category']
