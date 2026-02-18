from django.shortcuts import render, get_object_or_404
from .models import Product, Category
from django.shortcuts import render
from .models import Product, Category
from django.db.models import Q


def product_list(request):
    products = Product.objects.all()
    return render(request, 'products/list.html', {'products': products})


def home(request):
    category_id = request.GET.get('category')
    query = request.GET.get('q')

    #categories = Category.objects.all()
    categories = Category.objects.prefetch_related('subcategories')
    products = Product.objects.all()

    if category_id:
        products = products.filter(category_id=category_id)

    subcategory_id = request.GET.get('subcategory')
    if subcategory_id:
        products = products.filter(subcategory_id=subcategory_id)

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    return render(request, 'products/home.html', {
        'products': products,
        'categories': categories,
        'selected_category': category_id,
        'query': query,
    })

def product_detail(request, id):
    product = get_object_or_404(Product, id=id)
    categories = Category.objects.all()

    return render(request, 'products/product_detail.html', {
        'product': product,
        'categories': categories,
    })


from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Product, Category, SubCategory


def homepage(request):
    """
    Homepage view - shows featured products and category showcase
    """
    # Get all categories with product counts
    categories = Category.objects.all()
    for category in categories:
        category.product_count = Product.objects.filter(category=category).count()

    # Get featured products (you can customize this logic)
    # Option 1: Random featured products
    featured_products = Product.objects.all().order_by('?')[:6]

    # Option 2: Latest products
    # featured_products = Product.objects.all().order_by('-created_at')[:6]

    # Option 3: Products marked as featured (if you have a featured field)
    # featured_products = Product.objects.filter(featured=True)[:6]

    context = {
        'categories': categories,
        'featured_products': featured_products,
    }

    return render(request, 'index.html', context)


def categories_page(request):
    """
    Categories browsing page - shows all categories with their subcategories
    """
    # Get all categories with related subcategories
    categories = Category.objects.prefetch_related('subcategories').all()

    # Add product counts to each category
    for category in categories:
        category.product_count = Product.objects.filter(category=category).count()

        # Add product counts to subcategories
        for subcategory in category.subcategories.all():
            subcategory.product_count = Product.objects.filter(subcategory=subcategory).count()

    # Calculate total statistics
    total_subcategories = SubCategory.objects.count()
    total_products = Product.objects.count()

    context = {
        'categories': categories,
        'total_subcategories': total_subcategories,
        'total_products': total_products,
    }

    return render(request, 'products/categories.html', context)


def products_page(request):
    """
    Products page view - shows all products with filtering, search, and pagination
    """
    # Start with all products
    products = Product.objects.all()

    # Get filter parameters
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    subcategory_id = request.GET.get('subcategory', '')
    sort_by = request.GET.get('sort', 'featured')
    stock_filter = request.GET.get('stock', '')  # NEW: Get stock filter parameter

    # Apply search filter
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query)
        )

    # Apply category filter
    selected_category = None
    selected_category_name = None
    if category_id:
        products = products.filter(category_id=category_id)
        try:
            selected_category = int(category_id)
            category_obj = Category.objects.get(id=category_id)
            selected_category_name = category_obj.name
        except (ValueError, Category.DoesNotExist):
            pass

    # Apply subcategory filter
    selected_subcategory = None
    if subcategory_id:
        products = products.filter(subcategory_id=subcategory_id)
        try:
            selected_subcategory = int(subcategory_id)
            subcategory_obj = SubCategory.objects.get(id=subcategory_id)
            selected_category_name = subcategory_obj.name
        except (ValueError, SubCategory.DoesNotExist):
            pass

    # NEW: Apply stock filter
    if stock_filter == 'in-stock':
        products = products.filter(stock__gt=0)
    elif stock_filter == 'out-of-stock':
        products = products.filter(stock=0)

    # Apply sorting
    if sort_by == 'price-low':
        products = products.order_by('price')
    elif sort_by == 'price-high':
        products = products.order_by('-price')
    elif sort_by == 'name':
        products = products.order_by('name')
    else:  # featured or default
        products = products.order_by('-id')  # or any default ordering

    # Get total count before pagination
    total_products = products.count()

    # Pagination - 24 products per page
    paginator = Paginator(products, 24)  # You can change to 36, 48, etc.
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get all categories for sidebar
    categories = Category.objects.prefetch_related('subcategories').all()

    context = {
        'products': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'categories': categories,
        'query': query,
        'selected_category': selected_category,
        'selected_subcategory': selected_subcategory,
        'selected_category_name': selected_category_name,
        'total_products': total_products,
        'stock_filter': stock_filter,  # NEW: Pass stock filter to template

    }

    return render(request, 'products/products.html', context)