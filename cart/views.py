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

    return render(request, 'cart/cart.html', {
        'products': products,
        'total': total
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
