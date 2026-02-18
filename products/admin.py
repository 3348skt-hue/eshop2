from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Category,SubCategory, Product, Store

"""admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(Product)
admin.site.register(Store)
"""
from django.contrib import admin
from .models import Product, Store, Category, SubCategory


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'price', 'stock']
    list_filter = ['category', 'subcategory', 'store']
    search_fields = ['name', 'sku']


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