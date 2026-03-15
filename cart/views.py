from django.shortcuts import render, redirect, get_object_or_404
from products.models import Product

def add_to_cart(request, product_id):
    cart = request.session.get('cart', {})

    product = get_object_or_404(Product, id=product_id)

    if str(product_id) in cart:
        cart[str(product_id)] += 1
    else:
        cart[str(product_id)] = 1

    request.session['cart'] = cart

    #return redirect('cart_detail')
    return redirect('cart:cart_detail')


def cart_detail(request):
    from dashboard.models import ShippingRate
    cart = request.session.get('cart', {})
    products = []
    total = 0
    cleaned_cart = {}

    for product_id, qty in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            product.quantity = qty
            product.subtotal = qty * product.price
            total += product.subtotal
            products.append(product)
            cleaned_cart[product_id] = qty
        except Product.DoesNotExist:
            # silently remove deleted product
            continue

    request.session['cart'] = cleaned_cart
    request.session.modified = True

    shipping_rates = ShippingRate.objects.filter(is_active=True).order_by('country')
    return render(request, 'cart/cart.html', {
        'products': products,
        'total': total,
        'shipping_rates': shipping_rates,
    })


def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})

    product_id = str(product_id)

    if product_id in cart:
        del cart[product_id]
        request.session['cart'] = cart

    #return redirect('cart_detail')
    return redirect('cart:cart_detail')

from django.shortcuts import redirect

def increase_quantity(request, product_id):
    cart = request.session.get('cart', {})
    product_id = str(product_id)

    if product_id in cart:
        cart[product_id] += 1
    else:
        cart[product_id] = 1

    request.session['cart'] = cart

    #return redirect('cart_detail')
    return redirect('cart:cart_detail')


def decrease_quantity(request, product_id):
    cart = request.session.get('cart', {})
    product_id = str(product_id)

    if product_id in cart:
        cart[product_id] -= 1
        if cart[product_id] <= 0:
            del cart[product_id]

    request.session['cart'] = cart

    #return redirect('cart_detail')
    return redirect('cart:cart_detail')


from django.http import JsonResponse

from django.views.decorators.http import require_POST

@require_POST
def ajax_add_to_cart(request, product_id):
    cart = request.session.get('cart', {})
    product = get_object_or_404(Product, id=product_id)
    key = str(product_id)
    current_in_cart = cart.get(key, 0)
    if current_in_cart >= product.stock:
        return JsonResponse({
            'success': False,
            'error': 'max_stock',
            'message': f'Only {product.stock} unit(s) available. You already have {current_in_cart} in your cart.',
            'quantity': current_in_cart,
            'total_qty': sum(cart.values()),
            'product_name': product.name,
            'unit_price': float(product.price),
            'sku': product.sku,
        })
    cart[key] = current_in_cart + 1
    request.session['cart'] = cart
    request.session.modified = True
    total_qty = sum(cart.values())
    return JsonResponse({
        'success': True,
        'quantity': cart[key],
        'total_qty': total_qty,
        'product_name': product.name,
        'unit_price': float(product.price),
        'sku': product.sku,
    })

@require_POST
def ajax_update_cart(request, product_id, action):
    cart = request.session.get('cart', {})
    key = str(product_id)
    if action == 'increase':
        cart[key] = cart.get(key, 0) + 1
    elif action == 'decrease':
        cart[key] = cart.get(key, 1) - 1
        if cart[key] <= 0:
            del cart[key]
    request.session['cart'] = cart
    request.session.modified = True
    total_qty = sum(cart.values())
    qty = cart.get(key, 0)
    return JsonResponse({'success': True, 'quantity': qty, 'total_qty': total_qty})

def cart_data(request):
    cart = request.session.get('cart', {})
    from products.models import Product
    result = {}
    for pid, qty in cart.items():
        try:
            p = Product.objects.get(id=pid)
            result[str(pid)] = {
                'name': p.name,
                'qty': qty,
                'price': float(p.price),
                'sku': p.sku or ''
            }
        except Product.DoesNotExist:
            pass
    from django.http import JsonResponse
    return JsonResponse(result)
