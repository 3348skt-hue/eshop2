import os
from django.shortcuts import render
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.urls import reverse

import stripe
from django.conf import settings
from django.shortcuts import redirect, render
from products.models import Product
from .models import Order, OrderItem
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

stripe.api_key = settings.STRIPE_SECRET_KEY


@require_POST
def create_checkout_session(request):
    cart = request.session.get('cart')
    if not cart:
        return redirect('cart:cart_detail')

    full_name = request.POST.get('full_name')
    email = request.POST.get('email')
    phone = request.POST.get('phone')
    address_line1 = request.POST.get('address_line1')
    city = request.POST.get('address_city')
    postal_code = request.POST.get('address_postal_code')
    country = request.POST.get('address_country')

    if not full_name or not email or not address_line1 or not city or not postal_code or not country:
        return redirect('cart:cart_detail')

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

    delivery_type = request.POST.get('delivery_type', 'standard')
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
        cart_data[product_id] = {
            "name": product.name,
            "quantity": qty,
            "price": float(product.price)}

    if delivery_type == 'tracked':
        from dashboard.models import ShippingRate
        tracked_obj = ShippingRate.objects.filter(is_active=True, country=country).first()
        tracked_amount = int(float(tracked_obj.tracked_price) * 100) if tracked_obj else 1500
        line_items.append({
            "price_data": {
                "currency": "eur",
                "product_data": {"name": "Express Tracked Delivery (An Post)"},
                "unit_amount": tracked_amount,
            },
            "quantity": 1
        })

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=line_items,
        customer_email=email,
        billing_address_collection="required",
        phone_number_collection={"enabled": True},
        custom_text={
            "submit": {"message": "Your order will be dispatched from Dublin within 1-2 business days."},
            "after_submit": {"message": "Thank you for choosing MAK Supplies — your trusted medical instrument provider."}
        },
        success_url=request.build_absolute_uri(reverse("orders:order_success")) + "?session_id={CHECKOUT_SESSION_ID}",
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
    session_id = request.GET.get('session_id')
    order = None

    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            payment_intent = session.get('payment_intent')
            if payment_intent:
                try:
                    order = Order.objects.get(stripe_payment_intent=payment_intent)
                except Order.DoesNotExist:
                    import time
                    time.sleep(2)
                    try:
                        order = Order.objects.get(stripe_payment_intent=payment_intent)
                    except Order.DoesNotExist:
                        order = None
        except stripe.error.StripeError:
            pass

    if 'cart' in request.session:
        del request.session['cart']
    if 'checkout_info' in request.session:
        del request.session['checkout_info']

    context = {
        'order': order,
        'order_number': order.order_number if order else None,
    }

    return render(request, "orders/success.html", context)


from django_ratelimit.decorators import ratelimit

@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def order_lookup(request):
    order = None
    items = None
    error = None
    mysql_status = 'processing'

    if request.method == "POST":
        order_id = request.POST.get("order_id")
        email = request.POST.get("email")
        try:
            order = Order.objects.get(order_number=order_id, email=email)
            items = order.items.all()

            # Fetch status from MySQL
            import pymysql
            try:
                conn = pymysql.connect(
                    host="maksupplies.mysql.pythonanywhere-services.com",
                    user="maksupplies",
                    passwd=os.environ.get("DB_PASS", ""),
                    database="maksupplies$default",
                    autocommit=True
                )
                cursor = conn.cursor()
                cursor.execute("SELECT status, tracking_number FROM saleorder WHERE orderid=%s LIMIT 1", (order_id,))
                result = cursor.fetchone()
                if result:
                    if result[0]:
                        mysql_status = result[0]
                    tracking_number = result[1] if result[1] else None
                conn.close()
            except Exception as e:
                print(f"MySQL status fetch error: {e}")

        except Order.DoesNotExist:
            error = "Order not found"

    steps = [
        (1, 'Processing', 'fa-cog'),
        (2, 'Posted', 'fa-box'),
        (3, 'In Transit', 'fa-truck'),
        (4, 'Delivered', 'fa-check-circle'),
    ]
    status_step = {
        'processing': 1,
        'posted': 2,
        'in_transit': 3,
        'delivered': 4,
        'cancelled': 0,
    }
    current_step = status_step.get(mysql_status, 1)

    return render(request, "orders/order_lookup.html", {
        "order": order,
        "items": items,
        "error": error,
        "steps": steps,
        "current_step": current_step,
        "tracking_number": tracking_number if 'tracking_number' in dir() else None,
    })


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        return HttpResponse(status=400)

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

        import uuid
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4().hex)[:5].upper()
        order_number = f"ORD-{date_str}-{unique_id}"

        order = Order.objects.create(
            order_number=order_number,
            full_name=full_name,
            email=email,
            phone=phone,
            shipping_address=shipping_address,
            paid=True,
            stripe_payment_intent=session.get("payment_intent")
        )

        # Get cart from metadata to find SKUs
        cart = json.loads(session.get("metadata", {}).get("cart", "{}"))

        line_items = stripe.checkout.Session.list_line_items(session["id"])
        total_amount = 0
        order_items_data = []

        for item in line_items["data"]:
            product_name = item["description"]
            quantity = item["quantity"]
            unit_price = item["price"]["unit_amount"] / 100  # cents to euros

            # Find SKU and reduce Django stock
            sku = None
            for product_id, qty in cart.items():
                try:
                    product = Product.objects.get(id=product_id)
                    if product.name == product_name:
                        sku = product.sku
                        if product.stock >= quantity:
                            product.stock -= quantity
                            product.save()
                        break
                except Product.DoesNotExist:
                    pass

            OrderItem.objects.create(
                order=order,
                product_name=product_name,
                sku=sku,
                quantity=quantity,
                price=unit_price
            )

            order_items_data.append({
                "sku": sku,
                "quantity": quantity,
                "price": unit_price,
                "name": product_name
            })

            total_amount += item["amount_total"] / 100

        order.total = total_amount
        order.save()

        # Send confirmation email
        try:
            send_order_confirmation_email(order)
            print("Confirmation email sent!", flush=True)
        except Exception as e:
            print(f"Email error: {e}", flush=True)

        # Sync to MySQL and update eBay
        try:
            sync_order_to_mysql(order, order_items_data, shipping_address, email, full_name, phone)
        except Exception as e:
            print(f"MySQL sync error: {e}")

    return HttpResponse(status=200)


def send_order_confirmation_email(order):
    items = order.items.all()
    total = sum(item.price * item.quantity for item in items)
    context = {
        "full_name": order.full_name,
        "order_number": order.order_number,
        "items": items,
        "total": total,
        "address": order.shipping_address,
        "phone": order.phone,
    }
    html_content = render_to_string("emails/order_confirmation.html", context)
    email = EmailMultiAlternatives(
        subject=f"Order Confirmed - {order.order_number} | MAK Supplies",
        body=f"Thank you for your order {order.order_number}. Total: 20ac{total}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

    # Send admin notification
    items_text = "\n".join([f"- {item.product_name} x{item.quantity} @ €{item.price}" for item in items])
    admin_body = f"""New Order Received!

Order Number: {order.order_number}
Customer: {order.full_name}
Email: {order.email}
Phone: {order.phone}
Total: €{total}

Items:
{items_text}

Shipping Address:
{order.shipping_address.get('line1', '')}
{order.shipping_address.get('city', '')}
{order.shipping_address.get('postal_code', '')}
{order.shipping_address.get('country', '')}
"""
    admin_email = EmailMultiAlternatives(
        subject=f"🛒 New Order - {order.order_number} - €{total} - {order.full_name}",
        body=admin_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=["3348skt@gmail.com"],
    )
    admin_email.send()


def sync_order_to_mysql(order, items, shipping_address, email, full_name, phone):
    import pymysql

    connection = pymysql.connect(
        host="maksupplies.mysql.pythonanywhere-services.com",
        user="maksupplies",
        passwd=os.environ.get("DB_PASS", ""),
        database="maksupplies$default",
        autocommit=True,
        read_timeout=1000
    )
    cursor = connection.cursor()

    try:
        for item in items:
            sku = item['sku']
            quantity = item['quantity']
            price = item['price']
            product_name = item['name']

            if not sku:
                continue

            # Insert into saleorder
            sql = """INSERT INTO saleorder
                (userid, name, street1, city, postcode, country, phone, orderid,
                 total, quantity, time, site, currency, price, title, sku)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

            cursor.execute(sql, (
                email,
                full_name,
                shipping_address.get('line1', ''),
                shipping_address.get('city', ''),
                shipping_address.get('postal_code', ''),
                shipping_address.get('country', ''),
                phone,
                order.order_number,
                price,
                quantity,
                order.created_at.strftime('%Y-%m-%d'),
                'eshop',
                'EUR',
                price / quantity if quantity else price,
                product_name,
                sku
            ))

            # Update MySQL inventory stock
            cursor.execute(
                "UPDATE inventory SET stock = stock - %s, sale = sale + %s WHERE sku = %s",
                (quantity, quantity, sku)
            )

            # Get updated stock level
            cursor.execute("SELECT stock FROM inventory WHERE sku = %s", (sku,))
            result = cursor.fetchone()
            if result:
                new_stock = result[0]
                # Update eBay listings
                cursor.execute("SELECT itemid FROM ebaylisting WHERE sku = %s", (sku,))
                ebay_items = cursor.fetchall()
                for ebay_item in ebay_items:
                    try:
                        from ebaysdk.trading import Connection as Trading
                        api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')
                        api.execute('ReviseFixedPriceItem', {
                            'Item': {'ItemID': ebay_item[0], 'Quantity': new_stock}
                        })
                        print(f"eBay stock updated for item {ebay_item[0]}")
                    except Exception as e:
                        print(f"eBay update error: {e}")
    finally:
        connection.close()
