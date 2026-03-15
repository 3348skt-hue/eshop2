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

    featured_products = Product.objects.filter(stock__gt=0).order_by('?')[:6]

    return render(request, 'products/home.html', {
        'products': products,
        'featured_products': featured_products,
        'categories': categories,
        'selected_category': category_id,
        'query': query,
    })

def product_detail(request, id):
    from orders.models import OrderItem
    from django.db.models import Sum
    import pymysql, os
    product = get_object_or_404(Product, id=id)
    categories = Category.objects.all()
    # Django orders
    django_sold = OrderItem.objects.filter(sku=product.sku).aggregate(total=Sum("quantity"))["total"] or 0
    # MySQL orders (eBay + all)
    mysql_sold = 0
    try:
        conn = pymysql.connect(host="maksupplies.mysql.pythonanywhere-services.com", user="maksupplies", passwd=os.environ.get("DB_PASS",""), database="maksupplies$default", autocommit=True, read_timeout=3)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity) FROM saleorder WHERE sku=%s", (product.sku,))
        result = cursor.fetchone()
        mysql_sold = int(result[0]) if result and result[0] else 0
        conn.close()
    except: pass
    units_sold = max(django_sold, mysql_sold)
    return render(request, "products/product_detail.html", {
        "product": product,
        "categories": categories,
        "units_sold": units_sold,
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
    from orders.models import OrderItem
    from django.db.models import Sum, OuterRef, Subquery, IntegerField
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
            selected_category = subcategory_obj.category.id
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

    # Annotate units sold per product from Django orders
    from django.db.models import Sum, Value
    from django.db.models.functions import Coalesce
    sold_subquery = OrderItem.objects.filter(
        sku=OuterRef('sku')
    ).values('sku').annotate(total=Sum('quantity')).values('total')
    products = products.annotate(units_sold=Coalesce(Subquery(sold_subquery), Value(0)))

    # Get MySQL sales (eBay + all channels)
    import pymysql, os
    mysql_sales = {}
    try:
        conn = pymysql.connect(host="maksupplies.mysql.pythonanywhere-services.com", user="maksupplies", passwd=os.environ.get("DB_PASS",""), database="maksupplies$default", autocommit=True, read_timeout=3)
        cursor = conn.cursor()
        cursor.execute("SELECT sku, SUM(quantity) FROM saleorder GROUP BY sku")
        for row in cursor.fetchall():
            mysql_sales[str(row[0])] = int(row[1]) if row[1] else 0
        conn.close()
    except: pass

    # Merge MySQL sales into products
    products_list = list(products)
    for p in products_list:
        mysql_qty = mysql_sales.get(str(p.sku), 0)
        p.units_sold = max(p.units_sold, mysql_qty)

    # Pagination - 24 products per page
    paginator = Paginator(products, 24)  # You can change to 36, 48, etc.
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get all categories for sidebar
    categories = Category.objects.prefetch_related('subcategories').all()

    # Re-paginate with merged data
    from django.core.paginator import Paginator as Pag2
    paginator2 = Pag2(products_list, 24)
    page_obj = paginator2.get_page(page_number)

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

from django.core.mail import send_mail
from django.contrib import messages

from django_ratelimit.decorators import ratelimit

@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def contact_page(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:100]
        email = request.POST.get('email', '').strip()[:100]
        phone = request.POST.get('phone', '').strip()[:20]
        subject = request.POST.get('subject', '').strip()[:200]
        message = request.POST.get('message', '').strip()[:2000]
        if not all([name, email, subject, message]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'products/contact.html')

        try:
            send_mail(
                subject=f'MAK Supplies Contact: {subject}',
                message=f'''New contact form submission:

Name: {name}
Email: {email}
Phone: {phone}
Subject: {subject}

Message:
{message}''',
                from_email='3348skt@gmail.com',
                recipient_list=['3348skt@gmail.com'],
                fail_silently=False,
            )
            messages.success(request, 'success')
        except Exception as e:
            messages.error(request, f'error: {e}')

    return render(request, 'products/contact.html')


def shipping_page(request):
    from dashboard.models import ShippingRate
    rates = ShippingRate.objects.filter(is_active=True).order_by('country')
    free_countries = rates.filter(has_free_postage=True)
    tracked_only = rates.filter(has_free_postage=False)
    return render(request, "products/shipping.html", {
        'rates': rates,
        'free_countries': free_countries,
        'tracked_only': tracked_only,
    })

def returns_page(request):
    return render(request, "products/returns.html")



