from django.shortcuts import render
import json
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.urls import reverse

# Create your views here.
import stripe
from django.conf import settings
from django.shortcuts import redirect, render
from products.models import Product
from .models import Order, OrderItem

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(request):
    cart = request.session.get('cart')
    if not cart:
        return redirect('cart:cart_detail')

    # Get customer info from POST
    full_name = request.POST.get('full_name')
    email = request.POST.get('email')
    phone = request.POST.get('phone')
    address_line1 = request.POST.get('address_line1')
    city = request.POST.get('address_city')
    postal_code = request.POST.get('address_postal_code')
    country = request.POST.get('address_country')

    if not full_name or not email or not address_line1 or not city or not postal_code or not country:
        return redirect('cart:cart_detail')  # validate required fields

    # Store in session (so you can save Order in DB later)
    request.session['checkout_info'] = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "address": {
            "line1": address_line1,
            "city": city,
            "postal_code": postal_code,
            "country": country
        }
    }

    # Create Stripe line items
    line_items = []
    cart_data = {}
    for product_id, qty in cart.items():
        product = Product.objects.get(id=product_id)
        line_items.append({
            "price_data": {
                "currency": "eur",
                "product_data": {"name": product.name},
                "unit_amount": int(product.price * 100),
            },
            "quantity": qty
        })
        # 👇 Store in cart_data for webhook
        cart_data[product_id] = {
            "name": product.name,
            "quantity": qty,
            "price": float(product.price)}

    # Create Stripe Checkout session
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=line_items,
        customer_email=email,  # pre-fill Stripe email
        # shipping_address_collection={"allowed_countries": ["US", "GB", "DE", "FR", "NL", "ES"]},  # optional
        success_url=request.build_absolute_uri(reverse("orders:order_success")) + "?session_id={CHECKOUT_SESSION_ID}",
        # ✅ ADD SESSION_ID
        cancel_url=request.build_absolute_uri(reverse("cart:cart_detail")),
        metadata={
            "cart": json.dumps(cart),
            "full_name": full_name,
            "phone": phone,
            "address_line1": address_line1,
            "address_city": city,
            "address_postal_code": postal_code,
            "address_country": country,
        }
    )

    return redirect(session.url, code=303)


def order_success(request):
    """
    Display order confirmation with order number
    """
    # Get the session_id from URL parameter
    session_id = request.GET.get('session_id')

    order = None

    if session_id:
        try:
            # Retrieve the Stripe session
            session = stripe.checkout.Session.retrieve(session_id)

            # Get the payment intent ID
            payment_intent = session.get('payment_intent')

            # Find the order by payment intent
            if payment_intent:
                try:
                    order = Order.objects.get(stripe_payment_intent=payment_intent)
                except Order.DoesNotExist:
                    # Order might not be created yet by webhook
                    # Wait a moment and try again
                    import time
                    time.sleep(2)
                    try:
                        order = Order.objects.get(stripe_payment_intent=payment_intent)
                    except Order.DoesNotExist:
                        order = None
        except stripe.error.StripeError:
            pass

    # Clear the cart
    if 'cart' in request.session:
        del request.session['cart']
    if 'checkout_info' in request.session:
        del request.session['checkout_info']

    # ✅ PASS ORDER TO TEMPLATE
    context = {
        'order': order,
        'order_number': order.order_number if order else None,
    }

    return render(request, "orders/success.html", context)


def order_lookup(request):
    order = None
    items = None
    error = None

    if request.method == "POST":
        order_id = request.POST.get("order_id")
        email = request.POST.get("email")

        try:
            order = Order.objects.get(id=order_id, email=email)
            items = order.items.all()
        except Order.DoesNotExist:
            error = "Order not found"

    return render(request, "orders/order_lookup.html", {
        "order": order,
        "items": items,
        "error": error
    })


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        full_name = session.get("metadata", {}).get("full_name", "Unknown")
        email = session.get("customer_email", "unknown@email.com")
        phone = session.get("metadata", {}).get("phone", "")

        shipping_address = {
            "line1": session.get("metadata", {}).get("address_line1"),
            "city": session.get("metadata", {}).get("address_city"),
            "postal_code": session.get("metadata", {}).get("address_postal_code"),
            "country": session.get("metadata", {}).get("address_country"),
        }

        # ✅ GENERATE ORDER NUMBER
        import uuid
        from datetime import datetime

        date_str = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4().hex)[:5].upper()
        order_number = f"ORD-{date_str}-{unique_id}"

        # ✅ CREATE ORDER WITH ORDER NUMBER
        order = Order.objects.create(
            order_number=order_number,  # ✅ ADD THIS
            full_name=full_name,
            email=email,
            phone=phone,
            shipping_address=shipping_address,
            paid=True,
            stripe_payment_intent=session.get("payment_intent")
        )

        # ✅ GET ITEMS DIRECTLY FROM STRIPE
        line_items = stripe.checkout.Session.list_line_items(session["id"])

        total_amount = 0
        for item in line_items["data"]:
            product_name = item["description"]
            quantity = item["quantity"]
            price = item["amount_total"] / 100

            OrderItem.objects.create(
                order=order,
                product_name=product_name,
                quantity=quantity,
                price=price
            )

            total_amount += price

        # ✅ UPDATE ORDER TOTAL
        order.total = total_amount
        order.save()

    return HttpResponse(status=200)
