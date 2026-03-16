import csv
import io
from products.models import Product, Category, SubCategory, Store
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
import pymysql

def get_db():
    import os
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'maksupplies.mysql.pythonanywhere-services.com'),
        user=os.environ.get('DB_USER', 'maksupplies'),
        passwd=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'maksupplies$default'),
        autocommit=True,
        )

@staff_member_required
def index(request):
    conn = get_db()
    cursor = conn.cursor()

    # Orders
    cursor.execute("SELECT COUNT(*) FROM saleorder")
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM saleorder WHERE posted = '' OR posted IS NULL")
    unposted = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM saleorder WHERE DATE(time)=CURDATE()")
    today_orders = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total) FROM saleorder WHERE MONTH(time)=MONTH(NOW()) AND YEAR(time)=YEAR(NOW())")
    monthly_sales = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total) FROM saleorder WHERE YEAR(time)=YEAR(NOW())")
    yearly_sales = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total) FROM saleorder WHERE DATE(time)=CURDATE()")
    today_sales = cursor.fetchone()[0] or 0

    # Last 7 days sales trend
    cursor.execute("""
        SELECT DATE(time) as d, COUNT(*) as cnt, SUM(total) as rev
        FROM saleorder WHERE time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        GROUP BY DATE(time) ORDER BY d ASC
    """)
    sales_trend = cursor.fetchall()

    # Inventory
    cursor.execute("SELECT COUNT(*) FROM inventory")
    total_products = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE stock = 0")
    out_of_stock = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE stock <= reorder AND reorder > 0")
    low_stock = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(stock*price) FROM inventory")
    stock_value = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(stock*(price*(profit_margin/100))) FROM inventory WHERE profit_margin > 0")
    potential_profit = cursor.fetchone()[0] or 0

    # eBay
    cursor.execute("SELECT COUNT(*) FROM ebaylisting")
    total_listings = cursor.fetchone()[0]

    # Purchase Orders
    cursor.execute("SELECT COUNT(DISTINCT porder) FROM purchaseorder")
    total_pos = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT porder) FROM purchaseorder WHERE status='pending'")
    pending_pos = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total) FROM purchaseorder WHERE status='pending'")
    pending_po_value = cursor.fetchone()[0] or 0

    # Makers
    cursor.execute("SELECT COUNT(*) FROM maker")
    total_makers = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(debit)-SUM(credit) FROM maker_ledger")
    maker_balance = cursor.fetchone()[0] or 0

    # Recent orders
    cursor.execute("SELECT name, country, total, time FROM saleorder ORDER BY time DESC LIMIT 8")
    recent_orders = cursor.fetchall()

    # Low stock items
    cursor.execute("SELECT sku, title, stock, reorder FROM inventory WHERE stock <= reorder AND reorder > 0 ORDER BY stock ASC LIMIT 8")
    low_stock_items = cursor.fetchall()

    # Top selling SKUs this month
    cursor.execute("""
        SELECT i.sku, i.title, SUM(s.quantity) as units, SUM(s.total) as rev
        FROM saleorder s JOIN inventory i ON s.sku=i.sku
        WHERE MONTH(s.time)=MONTH(NOW()) AND YEAR(s.time)=YEAR(NOW())
        GROUP BY i.sku, i.title ORDER BY units DESC LIMIT 5
    """)
    top_skus = cursor.fetchall()

    # Recent POs
    cursor.execute("""
        SELECT porder, maker, SUM(total) as val, MIN(received_date) as dt,
               MAX(status) as status, COUNT(*) as line_count
        FROM purchaseorder GROUP BY porder, maker ORDER BY porder DESC LIMIT 5
    """)
    recent_pos = cursor.fetchall()

    # Stock movements today
    cursor.execute("SELECT COUNT(*) FROM stock_movement WHERE DATE(date)=CURDATE()")
    movements_today = cursor.fetchone()[0]

    conn.close()

    # Build 7-day trend list
    from datetime import date, timedelta
    trend_map = {str(r[0]): {'cnt': int(r[1]), 'rev': float(r[2] or 0)} for r in sales_trend}
    trend_days = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).strftime('%Y-%m-%d')
        day_label = (date.today() - timedelta(days=i)).strftime('%a')
        trend_days.append({'date': d, 'label': day_label, 'cnt': trend_map.get(d, {}).get('cnt', 0), 'rev': trend_map.get(d, {}).get('rev', 0)})
    max_rev = max((d['rev'] for d in trend_days), default=1) or 1

    return render(request, 'dashboard/index.html', {
        'total_orders': total_orders,
        'low_stock': low_stock,
        'unposted': unposted,
        'monthly_sales': round(float(monthly_sales), 2),
        'today_orders': today_orders,
        'today_sales': round(float(today_sales), 2),
        'total_products': total_products,
        'out_of_stock': out_of_stock,
        'stock_value': round(float(stock_value), 0),
        'potential_profit': round(float(potential_profit), 0),
        'total_listings': total_listings,
        'total_pos': total_pos,
        'pending_pos': pending_pos,
        'pending_po_value': round(float(pending_po_value), 0),
        'yearly_sales': round(float(yearly_sales), 2),
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
        'top_skus': top_skus,
        'recent_pos': recent_pos,
        'total_makers': total_makers,
        'maker_balance': round(float(maker_balance), 0),
        'movements_today': movements_today,
        'trend_days': trend_days,
        'max_rev': max_rev,
    })

@staff_member_required
def orders(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    filter_unposted = request.GET.get('unposted', '')
    if search:
        like = f"%{search}%"
        cursor.execute("""SELECT id,time,orderid,userid,name,sku,posted,quantity,
                         country,currency,price,total,site,comment,street1,street2,city,state,postcode,phone,status,tracking_number FROM saleorder
                         WHERE orderid LIKE %s OR userid LIKE %s OR sku LIKE %s
                         OR name LIKE %s OR country LIKE %s
                         ORDER BY time DESC LIMIT 100""", (like, like, like, like, like))
    elif filter_unposted:
        cursor.execute("""SELECT id,time,orderid,userid,name,sku,posted,quantity,
                         country,currency,price,total,site,comment,street1,street2,city,state,postcode,phone,status,tracking_number FROM saleorder
                         WHERE posted = '' OR posted IS NULL
                         ORDER BY time DESC""")
    else:
        cursor.execute("""SELECT id,time,orderid,userid,name,sku,posted,quantity,
                         country,currency,price,total,site,comment,street1,street2,city,state,postcode,phone,status,tracking_number FROM saleorder
                         ORDER BY time DESC LIMIT 50""")
    orders = cursor.fetchall()

    # Get customer order counts
    customer_emails = list(set([o[3] for o in orders if o[3]]))
    customer_counts = {}
    if customer_emails:
        format_strings = ','.join(['%s'] * len(customer_emails))
        cursor.execute(f"SELECT userid, COUNT(*) FROM saleorder GROUP BY userid HAVING userid IN ({format_strings})", customer_emails)
        for row in cursor.fetchall():
            customer_counts[row[0]] = row[1]

    # Append count to each order tuple
    orders = [o + (customer_counts.get(o[3], 1),) for o in orders]

    conn.close()
    return render(request, 'dashboard/orders.html', {
        'orders': orders,
        'search': search,
        'filter_unposted': filter_unposted,
    })

@staff_member_required
def mark_posted(request, order_id):
    if request.method == 'POST':
        tracking_number = request.POST.get('tracking_number', '')
        posted_date = request.POST.get('posted_date', '')
        conn = get_db()
        cursor = conn.cursor()
        posted_val = posted_date if posted_date else ''
        cursor.execute(
            "UPDATE saleorder SET posted=%s, tracking_number=%s WHERE id=%s",
            (posted_val, tracking_number, order_id)
        )
        conn.close()
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/orders/'))

@staff_member_required
def update_order_status(request, order_id):
    if request.method == 'POST':
        status = request.POST.get('status', 'processing')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE saleorder SET status=%s WHERE id=%s", (status, order_id))
        conn.close()
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/orders/'))

@staff_member_required  
def inventory(request):
    # pre-fetch makers for dropdown
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get("q", "")
    sort = request.GET.get("sort", "sku")
    direction = request.GET.get("dir", "asc")
    dir_sql = "ASC" if direction == "asc" else "DESC"
    order_map = {
        "sku": f"sku*1 {dir_sql}",
        "stock": f"stock {dir_sql}",
        "listing": f"listing {dir_sql}",
        "value": f"(stock*price) {dir_sql}",
        "sale": f"sale {dir_sql}",
        "price": f"price {dir_sql}",
        "weight": f"weight {dir_sql}",
        "reorder": f"reorder {dir_sql}",
        "title": f"title {dir_sql}",
        "maker": f"maker {dir_sql}",
        "all": "sku*1 ASC",
    }
    order_by = order_map.get(sort, "sku*1 ASC")
    if search:
        cursor.execute(f"""SELECT serial,sku,title,stock,sale,reorder,price,weight,maker,listing,(stock*price) as value,photo,catid,storecat,polish,packing,freight,postage,opening,comment,packing_type,cleaning,testing,profit_margin
                         FROM inventory WHERE sku = %s OR title LIKE %s OR maker LIKE %s
                         ORDER BY {order_by}""", (search, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute(f"""SELECT serial,sku,title,stock,sale,reorder,price,weight,maker,listing,(stock*price) as value,photo,catid,storecat,polish,packing,freight,postage,opening,comment,packing_type,cleaning,testing,profit_margin
                         FROM inventory ORDER BY {order_by}""")
    items_raw = cursor.fetchall()
    # Get real sold quantities from saleorder
    cursor.execute("SELECT sku, SUM(quantity) FROM saleorder GROUP BY sku")
    sold_map = {str(r[0]): int(r[1] or 0) for r in cursor.fetchall()}
    items = []
    for row in items_raw:
        sold = sold_map.get(str(row[1]), 0)
        items.append(row[:4] + (sold,) + row[5:])
    items_raw = None  # replace below fetchall
    # totals
    cursor.execute("SELECT SUM(stock*price), SUM(stock*weight) FROM inventory")
    totals = cursor.fetchone()
    total_value = round(float(totals[0] or 0), 2)
    total_weight = round(float(totals[1] or 0) / 1000, 2)
    cursor.execute("""
        SELECT maker,
               COUNT(*) as total_skus,
               SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock,
               SUM(CASE WHEN stock <= reorder AND reorder > 0 THEN 1 ELSE 0 END) as needs_reorder,
               SUM(stock) as total_stock
        FROM inventory
        WHERE maker != '' AND maker IS NOT NULL
        GROUP BY maker
        ORDER BY needs_reorder DESC, out_of_stock DESC
    """)
    maker_health = []
    for r in cursor.fetchall():
        total = int(r[1])
        oos = int(r[2])
        reorder = int(r[3])
        stock = int(r[4])
        pct = round((reorder / total) * 100) if total > 0 else 0
        if reorder > 0 or oos > 0:
            status = 'danger' if oos >= total * 0.5 else 'warning' if reorder > 0 else 'success'
            maker_health.append({
                'name': r[0],
                'total': total,
                'out_of_stock': oos,
                'needs_reorder': reorder,
                'total_stock': stock,
                'pct': pct,
                'status': status,
            })

    cursor.execute("SELECT id, name FROM maker ORDER BY name")
    makers = cursor.fetchall()
    # Get global rates

    # Get eBay listing sites per SKU
    cursor.execute("SELECT sku, GROUP_CONCAT(site) FROM ebaylisting GROUP BY sku")
    sku_sites = {str(r[0]): r[1] for r in cursor.fetchall()}

    items_with_suggested = []
    # Load settings from DB
    s = get_settings()
    PKR_EUR = float(s.get('pkr_to_eur', 180))
    FREIGHT_RATE = float(s.get('freight_rate', 1000))
    COMMISSION = float(s.get('commission', 25)) / 100
    PROFIT = 1 + float(s.get('profit_margin', 75)) / 100

    for item in items:
        buy_price = float(item[6] or 0)
        weight_g = float(item[7] or 0)
        polish = float(item[14] or 0) if len(item) > 14 else 0
        packing = float(item[15] or 0) if len(item) > 15 else 0
        item_profit = float(item[23] or 0) if len(item) > 23 else 0  # index 23 = profit_margin
        postage = float(item[17] or 0) if len(item) > 17 else 0
        cleaning = float(item[21] or 0) if len(item) > 21 else 0
        testing = float(item[22] or 0) if len(item) > 22 else 0
        freight = round(weight_g * FREIGHT_RATE / 1000, 2)
        total_pkr = buy_price + polish + packing + freight + cleaning + testing
        cost_eur = total_pkr / PKR_EUR
        item_profit_mult = 1 + (item_profit / 100) if item_profit > 0 else PROFIT
        sell_eur = round((cost_eur * item_profit_mult + postage) / (1 - COMMISSION), 2)
        sell_uk = round(sell_eur * 0.85, 2)
        sell_us = round(sell_eur * 1.08, 2)
        sell_ca = round(sell_eur * 1.48, 2)
        sell_au = round(sell_eur * 1.63, 2)
        sites = sku_sites.get(str(item[1]), '')
        items_with_suggested.append(item + (sell_eur, sell_uk, sell_us, sell_ca, sell_au, sites, round(buy_price,0), round(polish,2), round(packing,2), round(freight,2), round(total_pkr,0), round(cost_eur,2), round(postage,2), round(cleaning,2), round(testing,2)))

    conn.close()
    s = get_settings()
    conn2 = get_db()
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT MAX(porder) FROM purchaseorder")
    max_po = cursor2.fetchone()[0] or 25000
    next_po_num = int(max_po) + 1
    conn2.close()
    return render(request, "dashboard/inventory.html", {
        "items": items_with_suggested,
        "settings": s,
        "search": search,
        "sort": sort,
        "dir": direction,
        "maker_health": maker_health,
        "total_value": total_value,
        "total_weight": total_weight,
        "makers": makers,
        "rates": {
            'cleaning': {'value': 25},
            'testing': {'value': 30},
            'pkr_to_eur': {'value': 180},
            'freight_rate': {'value': 50},
            'ebay_commission': {'value': 25},
            'profit_margin': {'value': 100},
        },
        'next_po': next_po_num,
    })

@staff_member_required
def edit_inventory(request, item_id):
    with open('/tmp/edit_debug.txt', 'a') as f:
        f.write(f'EDIT_INVENTORY called: item_id={item_id} method={request.method}\n')
    if request.method == 'POST':
        stock = request.POST.get('stock')
        price = request.POST.get('price')
        reorder = request.POST.get('reorder')
        title = request.POST.get('title', '')
        opening = request.POST.get('opening', 0)
        weight = request.POST.get('weight', 0)
        postage = request.POST.get('postage', 0)
        comment = request.POST.get('comment', '')
        maker1 = request.POST.get('maker1', '')
        maker2 = request.POST.get('maker2', '')
        maker3 = request.POST.get('maker3', '')
        maker = ','.join(filter(None, [maker1, maker2, maker3]))
        conn = get_db()
        cursor = conn.cursor()
        catid = request.POST.get('catid', '')
        storecat = request.POST.get('storecat', '')
        photo = request.POST.get('photo', '')
        if request.FILES.get('photo_file'):
            import os
            photo_file = request.FILES['photo_file']
            sku_row = request.POST.get('sku', item_id)
            ext = os.path.splitext(photo_file.name)[1]
            filename = f"{sku_row}{ext}"
            filepath = f"/home/maksupplies/eshop2/media/products/{filename}"
            with open(filepath, 'wb+') as f:
                for chunk in photo_file.chunks():
                    f.write(chunk)
            photo = f"https://maksupplies.pythonanywhere.com/media/products/{filename}"
        polish = request.POST.get('polish', 0) or 0
        packing = request.POST.get('packing', 0) or 0
        packing_type = int(request.POST.get('packing_type', 0) or 0)
        profit_margin = float(request.POST.get('profit_margin', 0) or 0)
        freight = request.POST.get('freight', 0) or 0
        cleaning = request.POST.get('cleaning', 0) or 0
        testing = request.POST.get('testing', 0) or 0
        cursor.execute("""UPDATE inventory SET stock=%s, price=%s, reorder=%s, maker=%s,
                       photo=%s, catid=%s, storecat=%s, polish=%s, packing=%s, freight=%s,
                       title=%s, opening=%s, weight=%s, postage=%s, comment=%s,
                       cleaning=%s, testing=%s, profit_margin=%s, packing_type=%s
                       WHERE serial=%s""",
                       (stock, price, reorder, maker, photo, catid, storecat, polish, packing, freight,
                        title, opening, weight, postage, comment, cleaning, testing, profit_margin, packing_type, item_id))
        # Recalculate sell prices and sync to ebaylisting and eshop
        try:
            cursor.execute("SELECT sku, weight, polish, packing, freight, postage, cleaning, testing, profit_margin FROM inventory WHERE serial=%s", (item_id,))
            inv = cursor.fetchone()
            if inv:
                inv_sku = inv[0]
                s = get_settings()
                PKR_EUR = float(s.get('pkr_to_eur', 180))
                FREIGHT_RATE = float(s.get('freight_rate', 1000))
                COMMISSION = float(s.get('commission', 25)) / 100
                item_profit = float(inv[8] or 0)
                profit_mult = 1 + (item_profit / 100) if item_profit > 0 else 1 + float(s.get('profit_margin', 75)) / 100
                weight_g = float(inv[1] or 0)
                polish_v = float(inv[2] or 0)
                packing_v = float(inv[3] or 0)
                freight_v = float(inv[4] or 0) or round(weight_g * FREIGHT_RATE / 1000, 2)
                postage_v = float(inv[5] or 0)
                cleaning_v = float(inv[6] or 0)
                testing_v = float(inv[7] or 0)
                buy = float(price)
                total_pkr = buy + polish_v + packing_v + freight_v + cleaning_v + testing_v
                cost_eur = total_pkr / PKR_EUR
                base = (cost_eur * profit_mult + postage_v) / (1 - COMMISSION)
                prices_by_site = {
                    'ireland': round(base, 2),
                    'uk': round(base * 0.87, 2),
                    'usa': round(base * 1.08, 2),
                    'canada': round(base * 1.48, 2),
                    'australia': round(base * 1.63, 2),
                }
                # Update ebaylisting prices in DB
                for site, site_price in prices_by_site.items():
                    cursor.execute("UPDATE ebaylisting SET price=%s WHERE sku=%s AND LOWER(site)=%s",
                        (site_price, int(inv_sku), site))
                conn.commit()
                # Update eshop product price
                from products.models import Product as EshopProduct
                try:
                    EshopProduct.objects.filter(sku=str(inv_sku)).update(price=prices_by_site['ireland'])
                except Exception as e:
                    with open('/tmp/edit_debug.txt', 'a') as f: f.write(f'Eshop error: {e}\n')
                # Push new prices to eBay API
                try:
                    from ebaysdk.trading import Connection as Trading
                    api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')
                    cursor.execute("SELECT itemid, site FROM ebaylisting WHERE sku=%s", (int(inv_sku),))
                    listings = cursor.fetchall()
                    for itemid, site in listings:
                        site_key = (site or '').lower()
                        site_price = prices_by_site.get(site_key)
                        if site_price and itemid:
                            try:
                                api.execute('ReviseFixedPriceItem', {
                                    'Item': {
                                        'ItemID': itemid,
                                        'StartPrice': site_price
                                    }
                                })
                                cursor.execute("UPDATE ebaylisting SET price=%s WHERE itemid=%s", (site_price, itemid))
                            except Exception as e:
                                with open('/tmp/edit_debug.txt', 'a') as f: f.write(f'eBay item error {itemid}: {e}\n')
                except Exception as e:
                    with open('/tmp/edit_debug.txt', 'a') as f: f.write(f'eBay push error: {e}\n')
        except Exception as e:
            with open('/tmp/edit_debug.txt', 'a') as f: f.write(f'SYNC ERROR: {e}\n')
        # Sync stock to Django products_product table
        cursor.execute("SELECT sku FROM inventory WHERE serial=%s", (item_id,))
        row = cursor.fetchone()
        if row and maker:
            sku_val = row[0]
            maker_list = [m.strip() for m in maker.split(',') if m.strip()]
            if maker_list:
                cursor.execute("SELECT serial, makername FROM price WHERE sku=%s", (sku_val,))
                price_rows = cursor.fetchall()
                if price_rows:
                    if len(maker_list) == 1:
                        cursor.execute("UPDATE price SET makername=%s WHERE sku=%s", (maker_list[0], sku_val))
                    else:
                        cursor.execute("UPDATE price SET makername=%s WHERE sku=%s AND (makername='' OR makername IS NULL)", (maker_list[0], sku_val))
        if row and stock:
            sku = row[0]
            cursor.execute("UPDATE products_product SET stock=%s WHERE sku=%s", (stock, sku))
            # Sync stock to eBay listings
            try:
                from ebaysdk.trading import Connection as Trading
                api = Trading(config_file="/home/maksupplies/eshop2/ebay.yaml")
                cursor.execute("SELECT itemid FROM ebaylisting WHERE sku=%s", (sku,))
                listings = cursor.fetchall()
                for listing in listings:
                    api.execute("ReviseFixedPriceItem", {"Item": {"ItemID": listing[0], "Quantity": int(stock)}})
                print(f"eBay stock updated for SKU {sku} to {stock}")
            except Exception as e:
                print(f"eBay sync error: {e}")
        conn.close()
    return redirect(request.META.get("HTTP_REFERER", "/dashboard/inventory/"))

@staff_member_required
@staff_member_required
def purchase_orders(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    batch = request.GET.get('batch', '')

    # Fetch all batches for the filter dropdown
    cursor.execute("SELECT DISTINCT batch_id FROM purchaseorder WHERE batch_id != '' ORDER BY batch_id DESC")
    all_batches = [r[0] for r in cursor.fetchall()]

    if batch:
        cursor.execute(
            """SELECT sr, sku, qty, porder, price, item, size, maker, status, received_qty
               FROM purchaseorder
               WHERE batch_id = %s
               ORDER BY porder, sr""",
            (batch,)
        )
    elif search:
        cursor.execute(
            """SELECT sr, sku, qty, porder, price, item, size, maker, status, received_qty
               FROM purchaseorder
               WHERE maker LIKE %s OR sku LIKE %s OR porder LIKE %s
               ORDER BY sr DESC""",
            (search, f"%{search}%", f"%{search}%")
        )
    else:
        cursor.execute(
            """SELECT sr, sku, qty, porder, price, item, size, maker, status, received_qty
               FROM purchaseorder ORDER BY sr DESC LIMIT 150"""
        )
    raw_pos = cursor.fetchall()
    cursor.execute("SELECT MAX(porder) FROM purchaseorder")
    max_po = cursor.fetchone()[0] or 25000
    next_po = int(max_po) + 1
    skus = list({po[1] for po in raw_pos})
    stock_map = {}
    if skus:
        placeholders = ','.join(['%s'] * len(skus))
        cursor.execute(f"SELECT sku, stock FROM inventory WHERE sku IN ({placeholders})", skus)
        for row in cursor.fetchall():
            stock_map[row[0]] = row[1]

    pos = []
    for po in raw_pos:
        stock = stock_map.get(po[1], '-')
        total = round(float(po[4] or 0) * int(po[2] or 0))
        pos.append(po + (stock, total))

    # BY BATCH grouping
    cursor.execute("""
        SELECT batch_id, COUNT(*) as line_count, SUM(qty*price) as total, MIN(porder) as first_po, MAX(porder) as last_po, COUNT(DISTINCT maker) as maker_count, MIN(sr) as first_sr
        FROM purchaseorder WHERE batch_id != ''
        GROUP BY batch_id ORDER BY first_sr DESC
    """)
    batch_groups = []
    for r in cursor.fetchall():
        batch_groups.append({
            'batch_id': r[0], 'lines': r[1], 'total': round(r[2] or 0),
            'first_po': r[3], 'last_po': r[4], 'makers': r[5],
            'date': r[0][1:9] if len(r[0]) > 8 else r[0],
        })

    # BY MAKER grouping
    cursor.execute("""
        SELECT maker, COUNT(*) as line_count, SUM(qty*price) as total, COUNT(DISTINCT porder) as po_count
        FROM purchaseorder
        GROUP BY maker ORDER BY maker
    """)
    maker_groups = []
    for r in cursor.fetchall():
        maker_groups.append({
            'maker': r[0], 'lines': r[1], 'total': round(r[2] or 0), 'po_count': r[3],
        })

    conn.close()
    return render(request, 'dashboard/purchase_orders.html', {
        'pos': pos,
        'search': search,
        'next_po': next_po,
        'all_batches': all_batches,
        'current_batch': batch,
        'batch_groups': batch_groups,
        'maker_groups': maker_groups,
    })

@staff_member_required
def add_purchase_order(request):
    if request.method == 'POST':
        sku = request.POST.get('sku')
        qty = request.POST.get('qty')
        porder = request.POST.get('porder')
        price = request.POST.get('price')
        item = request.POST.get('item')
        size = request.POST.get('size')
        maker = request.POST.get('maker')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO purchaseorder (sku,qty,porder,price,item,size,maker)
                         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                       (sku, qty, porder, price, item, size, maker))
        conn.close()
    return redirect('/dashboard/purchase-orders/')

@staff_member_required
def ebay(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    if search:
        cursor.execute("""SELECT id,sku,itemid,site,price,status,title
                         FROM ebaylisting WHERE sku LIKE %s OR itemid LIKE %s OR title LIKE %s
                         ORDER BY sku""", (search, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""SELECT id,sku,itemid,site,price,status,title
                         FROM ebaylisting ORDER BY sku LIMIT 100""")
    listings = cursor.fetchall()
    conn.close()
    return render(request, 'dashboard/ebay.html', {
        'listings': listings,
        'search': search
    })

@staff_member_required
def update_ebay(request, listing_id):
    if request.method == 'POST':
        price = request.POST.get('price')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE ebaylisting SET price=%s WHERE id=%s", (price, listing_id))
        conn.close()
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/ebay/'))

# ============ LISTINGS VIEWS ============

eur = 1.00
us = 1.0847
uk = 0.8516
can = 1.4827
aus = 1.6375

@staff_member_required
def listings(request):
    return render(request, 'dashboard/listings.html')

@staff_member_required
def listing_stock_update(request):
    message = ''
    results = []
    if request.method == 'POST':
        sku = request.POST.get('sku')
        manual_qty = request.POST.get('manual_qty', '').strip()
        conn = get_db()
        cursor = conn.cursor()
        try:
            from ebaysdk.trading import Connection as Trading
            api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')
            if manual_qty:
                qty = int(manual_qty)
            else:
                cursor.execute("SELECT stock FROM inventory WHERE sku = %s", (sku,))
                result = cursor.fetchone()
                if not result:
                    message = f'SKU {sku} not found in inventory'
                    conn.close()
                    return render(request, 'dashboard/listing_stock.html', {'message': message})
                qty = result[0]
            cursor.execute("SELECT itemid, site FROM ebaylisting WHERE sku = %s", (sku,))
            listings = cursor.fetchall()
            for itemid, site in listings:
                try:
                    api.execute('ReviseFixedPriceItem', {'Item': {'ItemID': itemid, 'Quantity': qty}})
                    results.append({'site': site.upper(), 'itemid': itemid, 'status': 'Updated', 'success': True})
                except Exception as e:
                    results.append({'site': site.upper(), 'itemid': itemid, 'status': str(e), 'success': False})
            message = f'Stock set to {qty} on {len(listings)} listings'
        except Exception as e:
            message = f'Error: {str(e)}'
        conn.close()
    return render(request, 'dashboard/listing_stock.html', {'message': message, 'results': results})

@staff_member_required
def listing_price_update(request):
    message = ''
    results = []
    prices = {}
    if request.method == 'POST':
        sku = request.POST.get('sku')
        eur_price = float(request.POST.get('eur_price', 0))
        prices = {
            'ireland': round(eur_price * eur, 2),
            'uk': round(eur_price * uk, 2),
            'usa': round(eur_price * us, 2),
            'canada': round(eur_price * can, 2),
            'australia': round(eur_price * aus, 2),
        }
        conn = get_db()
        cursor = conn.cursor()
        try:
            from ebaysdk.trading import Connection as Trading
            api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')
            for site, price in prices.items():
                cursor.execute("SELECT itemid FROM ebaylisting WHERE sku = %s AND site = %s", (sku, site))
                row = cursor.fetchone()
                if row:
                    try:
                        api.execute('ReviseFixedPriceItem', {'Item': {'ItemID': row[0], 'StartPrice': str(price)}})
                        results.append({'site': site.upper(), 'price': price, 'status': 'Updated', 'success': True})
                    except Exception as e:
                        results.append({'site': site.upper(), 'price': price, 'status': str(e), 'success': False})
                else:
                    results.append({'site': site.upper(), 'price': price, 'status': 'No listing found', 'success': False})
            message = f'Price update complete for SKU {sku}'
        except Exception as e:
            message = f'Error: {str(e)}'
        conn.close()
    return render(request, 'dashboard/listing_price.html', {'message': message, 'results': results, 'prices': prices})

# ============ MAKER VIEWS ============

@staff_member_required
def makers(request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.id, m.name, m.address, m.mobile, m.landline, m.email,
               COUNT(DISTINCT i.sku) as item_count,
               SUM(i.stock) as total_stock,
               SUM(i.stock * i.price) as total_value
        FROM maker m
        LEFT JOIN inventory i ON FIND_IN_SET(m.name, i.maker) > 0
        GROUP BY m.id, m.name, m.address, m.mobile, m.landline, m.email
        ORDER BY m.name
    """)
    makers = cursor.fetchall()
    # Fetch outstanding balance per maker from ledger
    cursor.execute("""
        SELECT maker, balance FROM maker_ledger
        WHERE id IN (SELECT MAX(id) FROM maker_ledger GROUP BY maker)
    """)
    balance_map = {r[0]: float(r[1]) for r in cursor.fetchall()}
    conn.close()

    # Attach balance to each maker row (email is now m[5], item_count m[6], stock m[7], value m[8], balance m[9])
    makers_with_balance = []
    for m in makers:
        balance = balance_map.get(m[1], 0.0)
        makers_with_balance.append(m + (balance,))

    return render(request, 'dashboard/makers.html', {
        'makers': makers_with_balance,
        'balance_map': balance_map,
    })

@staff_member_required
def add_maker(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address')
        mobile = request.POST.get('mobile')
        landline = request.POST.get('landline')
        conn = get_db()
        cursor = conn.cursor()
        email = request.POST.get('email', '')
        cursor.execute("INSERT INTO maker (name, address, mobile, landline, email) VALUES (%s,%s,%s,%s,%s)",
                       (name, address, mobile, landline, email))
        conn.close()
    return redirect('/dashboard/makers/')

@staff_member_required
def edit_maker(request, maker_id):
    if request.method == 'POST':
        name = request.POST.get('name')
        address = request.POST.get('address')
        mobile = request.POST.get('mobile')
        landline = request.POST.get('landline')
        conn = get_db()
        cursor = conn.cursor()
        email = request.POST.get('email', '')
        cursor.execute("UPDATE maker SET name=%s, address=%s, mobile=%s, landline=%s, email=%s WHERE id=%s",
                       (name, address, mobile, landline, email, maker_id))
        conn.close()
    return redirect('/dashboard/makers/')

# ============ LISTING DESCRIPTION VIEW ============

@staff_member_required
def listing_description_update(request):
    message = ''
    results = []
    fetched_title = ''
    if request.method == 'POST':
        sku = request.POST.get('sku')
        size = request.POST.get('size')
        extra_specs = request.POST.get('extra_specs', '')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM inventory WHERE sku = %s", (sku,))
        row = cursor.fetchone()
        title = row[0] if row else ''
        fetched_title = title
        if not request.POST.get('do_update'):
            return render(request, 'dashboard/listing_description.html', {'message': '', 'results': [], 'fetched_title': fetched_title})
        try:
            from ebaysdk.trading import Connection as Trading
            api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')
            # Build spec rows
            spec_rows = f"<tr><td width='304'><b style='font-size:16pt'>Measurement</b></td><td width='304'><span style='font-size:21px'>{size}</span></td></tr>"
            if extra_specs:
                for spec in extra_specs.split('||'):
                    if '::' in spec:
                        k, v = spec.split('::', 1)
                        spec_rows += f"<tr><td><b style='font-size:16pt'>{k}</b></td><td><span style='font-size:16pt'>{v}</span></td></tr>"
            custom_title = request.POST.get('custom_title', title)
            desc = (
                "<![CDATA["
                "<div style='max-width:680px;margin:0 auto;font-family:Arial,sans-serif;color:#1a1a2e;background:#fff;'>"
                "<div style='background:linear-gradient(135deg,#6b0f1a,#8b1a2a,#a91b2e);padding:28px 32px;'>"
                "<div style='color:#f5c6cb;font-size:13px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;'>MAK Supplies - Professional Grade</div>"
                f"<h1 style='color:#ffffff;font-size:24px;font-weight:700;margin:0 0 10px;line-height:1.3;'>{custom_title}</h1>"
                "<div style='display:inline-block;background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.4);border-radius:4px;padding:5px 14px;color:#ffffff;font-size:13px;font-weight:600;'>ISO Certified &nbsp;|&nbsp; CE Approved &nbsp;|&nbsp; Autoclavable</div>"
                "</div>"
                "<div style='background:#fff0f3;border-left:5px solid #a91b2e;padding:16px 20px;display:table;width:100%;box-sizing:border-box;'>"
                "<div style='display:table-cell;vertical-align:middle;font-size:30px;width:40px;'>📏</div>"
                "<div style='display:table-cell;vertical-align:middle;padding-left:14px;'>"
                "<div style='font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;'>Measurement</div>"
                f"<div style='font-size:24px;font-weight:800;color:#1a1a2e;'>{size}</div>"
                "</div></div>"
                "<div style='padding:20px;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;margin-bottom:10px;border-bottom:2px solid #a91b2e;padding-bottom:6px;'>Specifications</div>"
                "<table style='width:100%;border-collapse:collapse;border:1px solid #e2e8f0;font-size:15px;'>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;width:45%;border-bottom:1px solid #e2e8f0;'>Material</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Premium Surgical Grade Stainless Steel</td></tr>"
                "<tr><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Finishing</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Satin / Matt Finish</td></tr>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Usage</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Reusable</td></tr>"
                "<tr><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Autoclave Safe</td><td style='padding:11px 14px;font-weight:700;color:#15803d;border-bottom:1px solid #e2e8f0;'>Yes - Fully Sterilisable</td></tr>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;'>Certifications</td><td style='padding:11px 14px;'>"
                "<span style='background:#6b0f1a;color:#fff;padding:3px 10px;border-radius:4px;font-weight:700;font-size:13px;margin-right:6px;'>ISO</span>"
                "<span style='background:#6b0f1a;color:#fff;padding:3px 10px;border-radius:4px;font-weight:700;font-size:13px;'>CE</span>"
                "</td></tr>"
                "</table>"
                "<div style='margin-top:16px;background:#fff8f8;border-radius:6px;padding:16px;border:1px solid #ffd0d5;font-size:15px;color:#334155;line-height:2;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;margin-bottom:10px;'>Quality Promise</div>"
                "&#10003; Each instrument individually inspected for highest possible quality.<br/>"
                "&#9632; Individually wrapped in protective polythene bag, packed in secure box for safe delivery.<br/>"
                "&#9889; <strong>Dispatched within 24 hours</strong> of cleared payment being received.<br/>"
                "<span style='color:#a91b2e;font-weight:700;'>Buy More, Save More!</span> Combine purchases for a discount — contact us via eBay."
                "</div>"
                "<div style='margin-top:14px;background:#f0fdf4;border-radius:6px;padding:16px;border:1px solid #bbf7d0;font-size:15px;color:#334155;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#15803d;margin-bottom:10px;'>Shipping &amp; Delivery</div>"
                "<table style='width:100%;border-collapse:collapse;font-size:15px;'>"
                "<tr style='background:#dcfce7;'><td style='padding:9px 12px;font-weight:700;color:#15803d;'>Ireland</td><td style='padding:9px 12px;color:#166534;font-weight:600;'>2-3 Business Days</td></tr>"
                "<tr><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>European Union</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>7-15 Business Days</td></tr>"
                "<tr style='background:#f0fdf4;'><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>Rest of Europe</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>10-20 Business Days</td></tr>"
                "<tr><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>Worldwide</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>10-26 Business Days</td></tr>"
                "</table>"
                "</div>"
                "<div style='margin-top:14px;background:#fff7ed;border-radius:6px;padding:16px;border:1px solid #fed7aa;font-size:15px;color:#334155;line-height:1.8;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#c2410c;margin-bottom:8px;'>Return Policy</div>"
                "Returns accepted within <strong>14 days</strong> of receipt. Items must be in original condition and packaging. Return postage covered by us.<br/>"
                "All items carefully inspected before dispatch. If shipping damage occurs, contact us immediately for a replacement."
                "</div>"
                "</div>"
                "<div style='background:linear-gradient(135deg,#6b0f1a,#8b1a2a,#a91b2e);padding:22px 28px;'>"
                "<div style='font-size:12px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#f5c6cb;margin-bottom:8px;'>About MAK Supplies</div>"
                "<p style='font-size:15px;color:#ffe0e4;margin:0 0 12px;line-height:1.7;'>We specialise in manufacturing surgical, dental, veterinary and manicure instruments. Upholding international trading standards, we deliver the highest quality with attentive customer service.</p>"
                "<div style='font-size:14px;color:#fca5a5;'>ISO &amp; CE Certified &nbsp;|&nbsp; Direct Manufacturer &nbsp;|&nbsp; Fast Worldwide Shipping &nbsp;|&nbsp; 14-Day Returns</div>"
                "</div>"
                "</div>"
                "]]>"
            )
            cursor.execute("SELECT itemid, site FROM ebaylisting WHERE sku = %s", (sku,))
            listings = cursor.fetchall()
            for itemid, site in listings:
                try:
                    api.execute('ReviseFixedPriceItem', {'Item': {'ItemID': itemid, 'Description': desc}})
                    results.append({'site': site.upper(), 'itemid': itemid, 'status': 'Updated', 'success': True})
                except Exception as e:
                    results.append({'site': site.upper(), 'itemid': itemid, 'status': str(e), 'success': False})
            message = f'Description updated on {len(listings)} listings for SKU {sku}'
        except Exception as e:
            message = f'Error: {str(e)}'
        conn.close()
    return render(request, 'dashboard/listing_description.html', {'message': message, 'results': results, 'fetched_title': fetched_title})

# ============ PRODUCT ADD/EDIT VIEWS ============

@staff_member_required
def add_product(request):
    conn = get_db()
    cursor = conn.cursor()
    message = ''
    fetched = {}
    if request.method == 'POST':
        sku = request.POST.get('sku')
        title = request.POST.get('title')
        stock = request.POST.get('stock')
        opening = request.POST.get('opening')
        reorder = request.POST.get('reorder')
        weight = request.POST.get('weight')
        postage = request.POST.get('postage')
        price = request.POST.get('price')
        maker = request.POST.get('maker')
        action = request.POST.get('action')
        if action == 'fetch':
            cursor.execute("SELECT title FROM ebaylisting WHERE sku = %s LIMIT 1", (sku,))
            row = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM ebaylisting WHERE sku = %s", (sku,))
            listing_count = cursor.fetchone()[0]
            cursor.execute("SELECT * FROM inventory WHERE sku = %s", (sku,))
            exists = cursor.fetchone()
            fetched = {
                'sku': sku,
                'title': row[0] if row else '',
                'listing_count': listing_count,
                'exists': exists is not None
            }
        else:
            photo = request.POST.get('photo', '')
            catid = request.POST.get('catid', '')
            storecat = request.POST.get('storecat', '')
            if request.FILES.get('photo_file'):
                import os
                photo_file = request.FILES['photo_file']
                ext = os.path.splitext(photo_file.name)[1]
                filename = f"{sku}{ext}"
                filepath = f"/home/maksupplies/eshop2/media/products/{filename}"
                with open(filepath, 'wb+') as f:
                    for chunk in photo_file.chunks():
                        f.write(chunk)
                photo = f"https://maksupplies.pythonanywhere.com/media/products/{filename}"
            cursor.execute("SELECT sku FROM inventory WHERE sku = %s", (sku,))
            if cursor.fetchone():
                message = f'SKU {sku} already exists in inventory!'
            else:
                cursor.execute("""INSERT INTO inventory (sku,title,price,opening,stock,reorder,weight,postage,maker,photo,catid,storecat)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                               (sku, title, price, opening, stock, reorder, weight, postage, maker, photo, catid, storecat))
                message = f'SKU {sku} added successfully!'
    cursor.execute("""
        SELECT maker,
               COUNT(*) as total_skus,
               SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock,
               SUM(CASE WHEN stock <= reorder AND reorder > 0 THEN 1 ELSE 0 END) as needs_reorder,
               SUM(stock) as total_stock
        FROM inventory
        WHERE maker != '' AND maker IS NOT NULL
        GROUP BY maker
        ORDER BY needs_reorder DESC, out_of_stock DESC
    """)
    maker_health = []
    for r in cursor.fetchall():
        total = int(r[1])
        oos = int(r[2])
        reorder = int(r[3])
        stock = int(r[4])
        pct = round((reorder / total) * 100) if total > 0 else 0
        if reorder > 0 or oos > 0:
            status = 'danger' if oos >= total * 0.5 else 'warning' if reorder > 0 else 'success'
            maker_health.append({
                'name': r[0],
                'total': total,
                'out_of_stock': oos,
                'needs_reorder': reorder,
                'total_stock': stock,
                'pct': pct,
                'status': status,
            })

    cursor.execute("SELECT id, name FROM maker ORDER BY name")
    makers = cursor.fetchall()
    conn.close()
    return render(request, 'dashboard/add_product.html', {
        'message': message,
        'fetched': fetched,
        'makers': makers
    })

@staff_member_required
def edit_product(request):
    conn = get_db()
    cursor = conn.cursor()
    message = ''
    product = None
    search = request.GET.get('sku', '')
    if search:
        cursor.execute("SELECT serial,sku,title,price,opening,stock,sale,reorder,weight,postage,listing,comment,maker FROM inventory WHERE sku = %s", (search,))
        product = cursor.fetchone()
    if request.method == 'POST':
        sku = request.POST.get('sku')
        fields = {
            'title': request.POST.get('title'),
            'price': request.POST.get('price'),
            'opening': request.POST.get('opening'),
            'stock': request.POST.get('stock'),
            'reorder': request.POST.get('reorder'),
            'weight': request.POST.get('weight'),
            'postage': request.POST.get('postage'),
            'comment': request.POST.get('comment'),
            'maker': request.POST.get('maker'),
        }
        for field, value in fields.items():
            if value:
                cursor.execute(f"UPDATE inventory SET {field} = %s WHERE sku = %s", (value, sku))
        message = f'SKU {sku} updated successfully!'
        cursor.execute("SELECT serial,sku,title,price,opening,stock,sale,reorder,weight,postage,listing,comment,maker FROM inventory WHERE sku = %s", (sku,))
        product = cursor.fetchone()
    cursor.execute("SELECT DISTINCT maker FROM inventory WHERE maker != '' ORDER BY maker")
    makers = [r[0] for r in cursor.fetchall()]
    conn.close()
    return render(request, 'dashboard/edit_product.html', {
        'product': product,
        'message': message,
        'search': search,
        'makers': makers
    })

# ============ CSV EXPORT ============
from django.http import HttpResponse, JsonResponse
import csv

@staff_member_required

def inventory_health(request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT maker,
               COUNT(*) as total_skus,
               SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock,
               SUM(CASE WHEN stock <= reorder AND reorder > 0 THEN 1 ELSE 0 END) as needs_reorder,
               SUM(stock) as total_stock,
               SUM(CASE WHEN stock > reorder THEN 1 ELSE 0 END) as healthy
        FROM inventory
        WHERE maker != '' AND maker IS NOT NULL
        GROUP BY maker
        ORDER BY needs_reorder DESC, out_of_stock DESC
    """)
    maker_health = []
    for r in cursor.fetchall():
        total = int(r[1])
        oos = int(r[2])
        reorder = int(r[3])
        stock = int(r[4])
        healthy = int(r[5])
        pct = round((reorder / total) * 100) if total > 0 else 0
        status = 'danger' if oos >= total * 0.5 else 'warning' if reorder > 0 else 'success'
        maker_health.append({
            'name': r[0],
            'total': total,
            'out_of_stock': oos,
            'needs_reorder': reorder,
            'total_stock': stock,
            'healthy': healthy,
            'pct': pct,
            'status': status,
        })

    # Overall stats
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN stock=0 THEN 1 ELSE 0 END), SUM(CASE WHEN stock<=reorder AND reorder>0 THEN 1 ELSE 0 END) FROM inventory")
    totals = cursor.fetchone()
    conn.close()
    return render(request, "dashboard/inventory_health.html", {
        "maker_health": maker_health,
        "total_skus": int(totals[0] or 0),
        "total_oos": int(totals[1] or 0),
        "total_reorder": int(totals[2] or 0),
    })

@staff_member_required
def inventory_csv(request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""SELECT sku,title,stock,sale,reorder,price,weight,postage,
                     maker,comment,photo,catid,storecat,polish,packing,freight,
                     opening,cleaning,testing,packing_type
                     FROM inventory ORDER BY sku*1 ASC""")
    items = cursor.fetchall()
    conn.close()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory.csv"'
    writer = csv.writer(response)
    writer.writerow(['sku','title','stock','sale','reorder','price','weight','postage',
                     'maker','comment','photo','catid','storecat','polish','packing','freight',
                     'opening','cleaning','testing','packing_size'])
    for item in items:
        pt = item[19] or 0
        if pt == 1:
            packing_size = 'Small'
        elif pt == 2:
            packing_size = 'Large'
        elif pt == 3:
            packing_size = 'Packet'
        else:
            # fallback to weight
            weight = item[6] or 0
            if weight <= 100:
                packing_size = 'Small'
            elif weight <= 500:
                packing_size = 'Large'
            else:
                packing_size = 'Packet'
        writer.writerow(list(item[:19]) + [packing_size])
    return response

# ============ BULK INVENTORY UPLOAD ============
import io

@staff_member_required
def inventory_bulk_upload(request):
    message = ''
    errors = []
    success_count = 0
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        conn = get_db()
        cursor = conn.cursor()
        for row in reader:
            try:
                sku = row.get('sku') or row.get('SKU')
                if not sku:
                    continue
                # Handle both exported CSV and manual CSV formats
                title = row.get('title', '')
                price = float(row.get('price') or 0)
                stock = int(float(row.get('stock') or 0))
                opening = int(float(row.get('opening') or row.get('stock') or 0))
                reorder = int(float(row.get('reorder') or 0))
                weight = float(row.get('weight') or 0)
                postage = float(row.get('postage') or 0)
                maker = row.get('maker', '')
                photo = row.get('photo', '')
                catid = row.get('catid', '')
                storecat = row.get('storecat', '')
                comment = row.get('comment', '')
                polish = float(row.get('polish') or 0)
                packing = float(row.get('packing') or 0)
                freight = float(row.get('freight') or 0)
                packing_size = (row.get('packing_type') or row.get('packing_size') or '').strip()
                if packing_size == 'Small': packing_type = 1
                elif packing_size == 'Large': packing_type = 2
                elif packing_size == 'Packet': packing_type = 3
                else: packing_type = 0

                cursor.execute("SELECT sku FROM inventory WHERE sku=%s", (sku,))
                exists = cursor.fetchone()
                if exists:
                    cursor.execute("""UPDATE inventory SET
                        title=%s, price=%s, opening=%s, stock=%s,
                        reorder=%s, weight=%s, postage=%s, maker=%s,
                        photo=%s, catid=%s, storecat=%s, comment=%s,
                        polish=%s, packing=%s, freight=%s, packing_type=%s
                        WHERE sku=%s""", (
                        title, price, opening, stock,
                        reorder, weight, postage, maker,
                        photo, catid, storecat, comment,
                        polish, packing, freight, packing_type, sku
                    ))
                else:
                    cursor.execute("""INSERT INTO inventory
                        (sku,title,price,opening,stock,reorder,weight,postage,maker,photo,catid,storecat,comment,polish,packing,freight,packing_type)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (
                        sku, title, price, opening, stock,
                        reorder, weight, postage, maker,
                        photo, catid, storecat, comment,
                        polish, packing, freight, packing_type
                    ))
                success_count += 1
            except Exception as e:
                errors.append(f'SKU {sku}: {str(e)}')
        conn.commit()
        conn.close()
        message = f'{success_count} products added/updated successfully!'
    return render(request, 'dashboard/inventory_bulk.html', {
        'message': message,
        'errors': errors,
        'success_count': success_count,
    })

# ============ DELETE PRODUCT ============

@staff_member_required
def delete_product(request, item_id):
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inventory WHERE serial=%s", (item_id,))
        conn.close()
        from django.contrib import messages
    messages.success(request, f"E-Shop Synchronization Complete.")
    return redirect('dashboard:inventory')

# ============ PRICE TABLE ============

@staff_member_required
def price_table(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    if search:
        cursor.execute("""SELECT serial,sku,name,makercode,makername,price,validfrom,validtill
                         FROM price WHERE sku LIKE %s OR name LIKE %s OR makername LIKE %s
                         ORDER BY sku*1, validfrom DESC""",
                       (search, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""SELECT serial,sku,name,makercode,makername,price,validfrom,validtill
                         FROM price ORDER BY sku*1, validfrom DESC""")
    prices = cursor.fetchall()
    cursor.execute("""
        SELECT maker,
               COUNT(*) as total_skus,
               SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock,
               SUM(CASE WHEN stock <= reorder AND reorder > 0 THEN 1 ELSE 0 END) as needs_reorder,
               SUM(stock) as total_stock
        FROM inventory
        WHERE maker != '' AND maker IS NOT NULL
        GROUP BY maker
        ORDER BY needs_reorder DESC, out_of_stock DESC
    """)
    maker_health = []
    for r in cursor.fetchall():
        total = int(r[1])
        oos = int(r[2])
        reorder = int(r[3])
        stock = int(r[4])
        pct = round((reorder / total) * 100) if total > 0 else 0
        if reorder > 0 or oos > 0:
            status = 'danger' if oos >= total * 0.5 else 'warning' if reorder > 0 else 'success'
            maker_health.append({
                'name': r[0],
                'total': total,
                'out_of_stock': oos,
                'needs_reorder': reorder,
                'total_stock': stock,
                'pct': pct,
                'status': status,
            })

    cursor.execute("SELECT id, name FROM maker ORDER BY name")
    makers = cursor.fetchall()
    conn.close()
    return render(request, 'dashboard/price_table.html', {
        'prices': prices,
        'search': search,
        'makers': makers,
    })

@staff_member_required
def add_price(request):
    if request.method == 'POST':
        sku = request.POST.get('sku')
        price = request.POST.get('price')
        makername = request.POST.get('makercode', '')
        validfrom = request.POST.get('validfrom') or None
        validtill = request.POST.get('validtill') or None
        conn = get_db()
        cursor = conn.cursor()
        # Get title from inventory
        cursor.execute("SELECT title FROM inventory WHERE sku=%s", (sku,))
        row = cursor.fetchone()
        title = row[0] if row else ''
        cursor.execute("""INSERT INTO price (sku,name,makercode,makername,price,validfrom,validtill)
                         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                       (sku, title, '', makername, price, validfrom, validtill))
        # Sync maker to inventory if not already there
        if makername:
            cursor.execute("SELECT maker FROM inventory WHERE sku=%s", (sku,))
            inv_row = cursor.fetchone()
            if inv_row:
                existing = inv_row[0] or ''
                makers_list = [m.strip() for m in existing.split(',') if m.strip()]
                if makername not in makers_list:
                    makers_list.append(makername)
                    cursor.execute("UPDATE inventory SET maker=%s WHERE sku=%s", 
                                  (','.join(makers_list), sku))
        conn.commit()
        conn.close()
    return redirect('/dashboard/price-table/')

@staff_member_required
def edit_price(request, price_id):
    if request.method == 'POST':
        price = request.POST.get('price')
        makername = request.POST.get('makername', '').strip()
        validfrom = request.POST.get('validfrom') or None
        validtill = request.POST.get('validtill') or None
        conn = get_db()
        cursor = conn.cursor()
        # Get sku for this price entry
        cursor.execute("SELECT sku FROM price WHERE serial=%s", (price_id,))
        row = cursor.fetchone()
        cursor.execute("UPDATE price SET price=%s, makername=%s, validfrom=%s, validtill=%s WHERE serial=%s",
                      (price, makername, validfrom, validtill, price_id))
        # Sync maker to inventory
        if row and makername:
            sku = row[0]
            cursor.execute("SELECT maker FROM inventory WHERE sku=%s", (sku,))
            inv_row = cursor.fetchone()
            if inv_row:
                existing = inv_row[0] or ''
                makers_list = [m.strip() for m in existing.split(',') if m.strip()]
                if makername not in makers_list:
                    makers_list.append(makername)
                    cursor.execute("UPDATE inventory SET maker=%s WHERE sku=%s",
                                  (','.join(makers_list), sku))
        conn.commit()
        conn.close()
    return redirect('/dashboard/price-table/')

@staff_member_required
def delete_price(request, price_id):
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price WHERE serial=%s", (price_id,))
        conn.close()
    return redirect('/dashboard/price-table/')

# ============ ORDERS REPORT ============

@staff_member_required
def orders_report(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    sort = request.GET.get('sort', 'date')

    sql = """SELECT s.time, s.orderid, s.userid, s.name, s.sku, s.posted,
             s.quantity, s.weight, s.country, s.currency, s.price,
             s.postcharge, s.total, s.fee, s.postage, s.rate, s.cost,
             s.title, s.comment, s.itemid, i.stock, s.id,
             i.price as buy_price, i.polish, i.packing
             FROM saleorder s
             LEFT JOIN inventory i ON s.sku = i.sku"""

    if search:
        sql += """ WHERE s.orderid LIKE %s OR s.userid LIKE %s OR s.sku LIKE %s
                   OR s.name LIKE %s OR s.country LIKE %s OR s.currency LIKE %s"""
        like = f"%{search}%"
        cursor.execute(sql + " ORDER BY s.time DESC LIMIT 500", (like,like,like,like,like,like))
    else:
        cursor.execute(sql + " ORDER BY s.time DESC LIMIT 500")

    rows = cursor.fetchall()

    # Build data with profit calculations
    orders = []
    total_euro = total_cost = total_post = total_profit = total_fee_charges = 0


    for r in rows:
        try:
            quantity = float(r[6] or 1)
            price = float(r[10] or 0)
            postcharge = float(r[11] or 0)
            fee = float(r[13] or 0)
            postage = float(r[14] or 0)
            weight_g = float(r[7] or 0)
            country = r[8] or ''
            if postage == 0:
                postage = get_postage_cost(country, weight_g)
            rate = float(r[15] or 1)
            currency = r[9] or 'EUR'
            buy_price = float(r[22] or 0)
            polish = float(r[23] or 0)
            packing = float(r[24] or 0)
            s = get_settings()
            PKR_EUR = float(s.get('pkr_to_eur', 180))
            FREIGHT_RATE = float(s.get('freight_rate', 1000))
            freight = round(weight_g * FREIGHT_RATE / 1000, 2)
            total_pkr = buy_price + polish + packing + freight
            actual_cost_eur = total_pkr / PKR_EUR if PKR_EUR else float(r[16] or 0) * quantity
            fee2 = 0.43 if currency == 'EUR' else 0.36
            fee_total = fee + fee2
            total_val = price * quantity + postcharge
            gross = total_val - fee_total
            euro = total_val * rate
            net = gross * rate
            profit = net - actual_cost_eur - postage
            fee_pct = (fee_total / total_val * 100) if total_val > 0 else 0
            profit_pct = (profit / actual_cost_eur * 100) if actual_cost_eur > 0 else 0
            ebay_charges = fee * rate

            total_euro += euro
            total_cost += actual_cost_eur
            total_post += postage
            total_profit += profit
            total_fee_charges += fee_total

            orders.append({
                'db_id': r[21], 'date': r[0], 'orderid': r[1], 'userid': r[2],
                'name': r[3], 'sku': r[4], 'posted': r[5], 'qty': int(quantity),
                'weight': r[7], 'country': r[8], 'currency': currency,
                'price': round(price,2), 'postcharge': round(postcharge,2),
                'total': round(total_val,2), 'fee': round(fee_total,2),
                'fee_pct': round(fee_pct,1), 'gross': round(gross,2),
                'rate': round(rate,2), 'euro': round(euro,2),
                'cost': round(actual_cost_eur,2), 'cost_pkr': round(total_pkr,0),
                'buy_price': round(buy_price,0), 'polish': round(polish,0),
                'packing': round(packing,0), 'freight': round(freight,0),
                'post': round(postage,2), 'profit': round(profit,2),
                'profit_pct': round(profit_pct,1), 'ebay_charges': round(ebay_charges,2),
                'title': r[17], 'comment': r[18], 'itemid': r[19], 'stock': r[20],
            })
        except Exception as e:
            print(f"ROW ERROR {r[4]}: {e}")
            import traceback; traceback.print_exc()
            continue

    # Sort
    if sort == 'stock':
        orders.sort(key=lambda x: x['stock'] or 0)
    elif sort == 'date':
        orders.sort(key=lambda x: str(x['date']), reverse=True)
    elif sort == 'profit_pct':
        orders.sort(key=lambda x: x['profit_pct'], reverse=True)
    elif sort == 'fee_pct':
        orders.sort(key=lambda x: x['fee_pct'])

    # Country breakdown
    country_counts = {}
    currency_counts = {}
    sku_counts = {}
    for o in orders:
        country_counts[o['country']] = country_counts.get(o['country'], 0) + 1
        currency_counts[o['currency']] = currency_counts.get(o['currency'], 0) + 1
        sku_counts[o['sku']] = sku_counts.get(o['sku'], 0) + o['qty']

    country_counts = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
    currency_counts = sorted(currency_counts.items(), key=lambda x: x[1], reverse=True)
    sku_counts = sorted(sku_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    total_euro = round(total_euro, 2)
    profit_pct_avg = round((total_profit / total_euro * 100), 1) if total_euro > 0 else 0
    post_pct = round((total_post / total_euro * 100), 1) if total_euro > 0 else 0
    cost_pct = round((total_cost / total_euro * 100), 1) if total_euro > 0 else 0

    conn.close()
    return render(request, 'dashboard/orders_report.html', {
        'orders': orders,
        'search': search,
        'sort': sort,
        'total_euro': total_euro,
        'total_cost': round(total_cost, 2),
        'total_post': round(total_post, 2),
        'total_profit': round(total_profit, 2),
        'profit_pct_avg': profit_pct_avg,
        'post_pct': post_pct,
        'cost_pct': cost_pct,
        'total_fee_charges': round(total_fee_charges, 2),
        'country_counts': country_counts,
        'currency_counts': currency_counts,
        'sku_counts': sku_counts,
    })

# ============ EDIT ORDER ============

@staff_member_required
def edit_order(request, order_id):
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        fields = {
            'comment': request.POST.get('comment'),
            'cost': request.POST.get('cost'),
            'rate': request.POST.get('rate'),
            'postage': request.POST.get('postage'),
            'posted': request.POST.get('posted'),
            'price': request.POST.get('price'),
            'fee': request.POST.get('fee'),
        }
        for field, value in fields.items():
            if value is not None and value != '':
                cursor.execute(f"UPDATE saleorder SET {field}=%s WHERE id=%s", (value, order_id))
        conn.close()
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/orders/report/'))

# ============ CREATE EBAY LISTING ============

sku_list = {'39298':'2832','61340':'2831','1270':'2830','61430':'2829','63110':'2828','55160':'2827','17742':'2826','51350':'2825','17450':'2824','17381':'2823','6157':'2822','1371':'2821','6260':'2820','6164':'2819','41114':'2818','13270':'2817','29500':'2816','15140':'2815','15142':'2814','15141':'2813','15130':'2812','15290':'2811','15210':'2810','15132':'2809','15145':'2808','15146':'2807','1100':'5','1110':'10','1112':'11','1140':'14','1250':'15','1260':'16','1300':'19','1310':'24','1320':'27','1330':'31','1340':'35','1350':'39','1360':'44','1370':'49','1380':'54','3140':'57','3142':'61','3144':'65','3150':'70','5152':'74','5230':'78','5240':'80','5250':'86','5260':'91','6100':'95','6101':'97','6102':'101','6103':'106','6104':'110','6105':'113','6106':'116','6107':'119','6109':'123','6110':'127','6112':'131','6113':'135','6114':'139','6115':'143','6116':'147','6117':'149','6118':'153','6119':'157','6120':'161','6121':'165','6122':'169','6123':'173','6128':'175','6131':'179','6140':'184','6141':'188','6143':'192','6152':'196','6153':'200','6154':'204','6159':'206','6160':'210','6161':'214','6162':'218','6163':'220','6165':'222','6166':'226','6167':'230','6168':'234','6169':'238','6170':'242','6171':'246','6173':'251','6174':'256','6175':'261','6176':'265','6178':'269','6183':'272','6186':'274','6187':'278','6188':'282','6189':'287','6190':'291','6192':'295','6193':'299','6195':'303','6196':'307','6197':'311','6198':'315','6199':'319','6200':'324','6201':'328','6202':'332','6210':'336','6211':'337','6212':'340','6213':'343','6214':'347','6216':'351','6217':'355','6218':'359','6219':'363','6220':'367','6221':'370','6224':'374','6225':'378','6226':'382','6227':'386','6228':'390','6229':'392','6230':'393','6231':'394','6234':'398','6235':'399','6236':'400','6237':'401','6238':'402','6239':'403','6240':'408','6241':'412','6242':'416','6243':'421','6244':'425','6245':'429','6250':'433','6251':'437','6252':'441','6253':'445','6254':'449','6255':'451','6256':'452','6257':'456','6261':'460','6270':'464','6271':'468','6272':'472','6273':'476','6274':'480','7105':'484','7107':'489','11100':'494','11120':'499','13100':'504','13102':'508','13104':'513','13106':'518','13108':'523','13110':'528','13112':'533','13114':'538','13116':'543','13118':'548','13120':'553','13122':'558','13124':'563','13126':'568','13128':'573','13130':'578','13132':'583','13134':'588','13136':'593','13138':'598','13140':'604','13142':'609','13144':'614','13146':'619','13148':'624','13150':'629','13152':'634','13154':'639','13156':'644','13158':'649','13170':'654','13172':'659','13180':'663','13182':'668','13184':'673','13186':'679','13190':'684','13193':'689','13194':'694','13196':'699','13200':'704','13202':'708','13210':'713','13212':'718','13220':'721','13222':'725','13230':'730','13232':'735','13240':'739','13242':'742','13244':'746','13248':'749','13250':'753','13252':'757','13254':'762','13258':'765','13259':'769','13260':'773','13262':'777','13280':'782','13290':'787','13310':'792','13312':'796','13320':'801','13340':'804','13345':'805','13350':'809','13360':'814','13370':'819','13380':'824','13402':'829','13410':'833','13420':'838','13430':'843','13432':'848','13440':'853','13442':'858','13452':'863','13454':'867','13462':'872','13464':'877','13470':'882','13472':'887','13482':'892','13486':'897','13502':'902','13506':'907','13520':'910','13522':'913','13530':'918','13532':'923','13540':'928','13542':'933','13550':'938','13560':'943','13562':'947','13570':'951','13572':'955','13582':'960','13590':'964','13592':'969','15106':'973','15121':'977','15122':'980','15123':'983','15124':'986','15125':'989','15126':'992','15143':'995','15144':'998','15200':'1001','15202':'1003','15204':'1004','15212':'1006','15214':'1009','15220':'1012','15230':'1015','15280':'1018','15300':'1020','15310':'1022','15320':'1026','15322':'1029','15330':'1032','15380':'1036','15382':'1040','15384':'1044','15390':'1048','15400':'1052','15420':'1056','15422':'1059','15490':'1064','15500':'1069','15502':'1073','15503':'1077','15520':'1082','17120':'1086','17122':'1090','17140':'1095','17142':'1100','17150':'1104','17152':'1109','17160':'1110','17162':'1114','17170':'1118','17172':'1122','17180':'1126','17182':'1130','17190':'1135','17192':'1140','17200':'1145','17202':'1150','17210':'1155','17212':'1160','17214':'1165','17240':'1170','17242':'1175','17250':'1180','17251':'1185','17252':'1190','17255':'1195','17257':'1199','17260':'1204','17261':'1208','17262':'1213','17265':'1218','17300':'1223','17310':'1228','17320':'1233','17340':'1238','17370':'1243','17373':'1248','17380':'1253','17383':'1258','17388':'1260','17391':'1265','17392':'1270','17393':'1275','17396':'1280','17401':'1285','17402':'1290','17403':'1295','17410':'1300','17412':'1305','17420':'1310','17422':'1315','17480':'1320','17572':'1324','17592':'1329','17600':'1334','17612':'1339','17620':'1344','17630':'1348','17670':'1353','17680':'1358','17690':'1362','17720':'1367','17740':'1372','17752':'1377','17760':'1381','17764':'1386','17820':'1391','17840':'1396','17860':'1401','17890':'1406','17910':'1411','17912':'1416','17914':'1420','19800':'1425','19802':'1429','19804':'1434','19806':'1438','19820':'1443','19880':'1447','19890':'1451','19910':'1456','19912':'1460','19920':'1464','19922':'1465','19930':'1470','19932':'1474','19950':'1478','19962':'1483','19990':'1487','19992':'1491','21100':'1495','21102':'1499','21110':'1503','21120':'1507','21132':'1509','21136':'1511','21143':'1515','21144':'1519','21146':'1523','21147':'1527','21148':'1531','21149':'1536','21152':'1540','21153':'1544','21154':'1548','21155':'1552','21156':'1556','21157':'1560','21173':'1564','21178':'1568','21190':'1572','21210':'1577','21220':'1581','21248':'1585','21249':'1589','21253':'1593','21254':'1597','21255':'1602','21256':'1606','21257':'1610','21270':'1615','21290':'1620','21300':'1625','21310':'1629','21330':'1634','21340':'1638','21342':'1642','21344':'1646','21351':'1650','21352':'1654','21353':'1658','21360':'1663','21381':'1667','21382':'1671','21383':'1675','21410':'1680','21412':'1684','21420':'1688','21422':'1692','21424':'1697','21426':'1701','21430':'1706','21440':'1710','21450':'1715','21460':'1720','21470':'1725','21480':'1729','21490':'1734','23132':'1738','23150':'1743','23212':'1746','23214':'1749','25100':'1754','25130':'1759','25131':'1763','25132':'1768','25133':'1772','25134':'1776','25135':'1780','25140':'1786','25180':'1790','25190':'1795','25200':'1800','25220':'1805','25230':'1810','25260':'1815','25262':'1819','25264':'1823','25270':'1828','25281':'1832','25282':'1837','25420':'1842','27104':'1845','27120':'1850','27150':'1855','27170':'1859','27180':'1863','27192':'1868','27200':'1873','27220':'1878','29100':'1883','29110':'1888','29142':'1892','29144':'1896','29146':'1900','29201':'1903','29202':'1906','29211':'1910','29212':'1914','29213':'1918','29240':'1922','29280':'1925','29290':'1928','29330':'1931','29390':'1936','29400':'1941','29420':'1946','29460':'1951','29470':'1956','29480':'1962','29510':'1967','29520':'1971','29522':'1976','29540':'1981','29550':'1985','29560':'1989','29570':'1994','29582':'1999','29590':'2005','29602':'2009','29612':'2012','29620':'2017','29622':'2020','29630':'2024','29632':'2028','31120':'2032','33160':'2036','33170':'2040','35112':'2045','35130':'2050','35160':'2055','35170':'2059','37190':'2064','37192':'2069','37194':'2074','37196':'2079','37280':'2084','37360':'2089','37370':'2094','37380':'2099','37382':'2104','37384':'2109','37420':'2114','37460':'2115','37520':'2119','39100':'2121','39110':'2125','39120':'2129','39210':'2134','39212':'2139','39220':'2144','39290':'2148','39295':'2153','39300':'2158','41100':'2163','41102':'2168','41104':'2172','41110':'2177','41112':'2181','41116':'2182','41122':'2187','41180':'2192','41188':'2196','41189':'2200','41190':'2204','41200':'2208','41240':'2213','41257':'2218','41270':'2222','41290':'2226','41300':'2230','41310':'2234','41410':'2239','41420':'2244','41430':'2249','41460':'2254','41470':'2259','41520':'2264','41521':'2269','41522':'2274','41523':'2278','43100':'2280','43102':'2282','43110':'2287','43140':'2289','43142':'2291','43150':'2295','43152':'2299','43170':'2304','43190':'2309','43250':'2313','43272':'2318','43290':'2324','43310':'2329','45170':'2334','45190':'2339','45240':'2343','47131':'2347','49131':'2351','49132':'2356','49133':'2361','51100':'2366','51150':'2371','51160':'2376','51182':'2380','51200':'2384','51210':'2389','51220':'2394','51230':'2399','51250':'2404','51252':'2409','51260':'2414','51292':'2419','51352':'2424','51382':'2425','51520':'2428','53100':'2432','53115':'2436','53120':'2440','53160':'2444','53162':'2451','55130':'2456','55132':'2460','55166':'2464','57120':'2466','57230':'2471','61100':'2475','61102':'2479','61103':'2483','61104':'2487','61105':'2491','61110':'2495','61112':'2499','61113':'2503','61114':'2507','61120':'2511','61122':'2515','61124':'2519','61126':'2523','61127':'2527','61128':'2531','61130':'2533','61132':'2535','61134':'2537','61136':'2541','61137':'2545','61140':'2547','61142':'2549','61144':'2553','61146':'2559','61150':'2563','61152':'2565','61154':'2567','61190':'2569','61192':'2570','61194':'2572','61196':'2575','61220':'2577','61280':'2582','61290':'2587','61300':'2591','61390':'2592','61400':'2594','61410':'2595','61450':'2600','61480':'2605','61490':'2610','61510':'2615','61540':'2620','61542':'2625','61550':'2630','61560':'2635','61562':'2637','61630':'2642','61632':'2647','61710':'2652','61730':'2657','61760':'2662','61770':'2666','61790':'2670','61800':'2675','61822':'2680','61823':'2684','61824':'2688','61825':'2689','61950':'2693','61970':'2698','63100':'2700','63120':'2703','63130':'2708','63140':'2712','63142':'2716','63150':'2720','63172':'2725','63180':'2729','63182':'2733','63200':'2738','63220':'2742','63250':'2747','63450':'2749','63460':'2752','63550':'2757','75100':'2761','75105':'2765','75111':'2768','75112':'2771','191000':'2775','191002':'2779','191010':'2783','191012':'2787','191020':'2792','191022':'2796','191040':'2800','191042':'2804','51342':'2805','15120':'2806'}

@staff_member_required
def create_listing(request):
    conn = get_db()
    cursor = conn.cursor()
    message = ''
    results = []
    sheet_data = None
    step = request.POST.get('step', '1')

    if request.method == 'POST' and step == '1':
        sku1 = request.POST.get('sku', '').strip()
        cursor.execute("SELECT sku, title, price, stock, photo, catid, storecat, weight, polish, packing, postage, cleaning, testing FROM inventory WHERE sku=%s", (sku1,))
        inv = cursor.fetchone()
        if not inv:
            message = f'SKU {sku1} not found in inventory'
        else:
            # Calculate sell price
            s = get_settings()
            PKR_EUR = float(s.get('pkr_to_eur', 180))
            FREIGHT_RATE = float(s.get('freight_rate', 1000))
            PROFIT = 1 + float(s.get('profit_margin', 75)) / 100
            COMMISSION = float(s.get('commission', 25)) / 100
            buy_price = float(inv[2] or 0)
            weight_g = float(inv[7] or 0)
            polish = float(inv[8] or 0)
            packing = float(inv[9] or 0)
            postage = float(inv[10] or 0)
            cleaning = float(inv[11] or 0)
            testing = float(inv[12] or 0)
            freight = round(weight_g * FREIGHT_RATE / 1000, 2)
            total_pkr = buy_price + polish + packing + freight + cleaning + testing
            cost_eur = total_pkr / PKR_EUR
            sell_price = round((cost_eur * PROFIT + postage) / (1 - COMMISSION), 2)

            cursor.execute("SELECT site FROM ebaylisting WHERE sku=%s", (sku1,))
            existing = [r[0] for r in cursor.fetchall()]
            sheet_data = {
                'sku': inv[0],
                'title': inv[1],
                'price': sell_price,
                'stock': inv[3],
                'photo': inv[4],
                'cat_id': inv[5],
                'store_cat': inv[6],
                'existing': existing,
                'sites': ['ireland','uk','usa','canada','australia'],
            }

    elif request.method == 'POST' and step == '2':
        sku1 = request.POST.get('sku')
        cat_id = request.POST.get('cat_id')
        title = request.POST.get('title')
        photo = request.POST.get('photo')
        store_cat = request.POST.get('store_cat')
        size = request.POST.get('size')
        eur_price = float(request.POST.get('eur_price', 0))
        qty = int(request.POST.get('qty', 1))
        sites = request.POST.getlist('sites')
        verify_only = request.POST.get('verify_only') == '1'

        live = get_live_rates()
        eurp=1.00; ukp=live['GBP']; usp=live['USD']; canp=live['CAD']; ausp=live['AUD']
        prices = {
            'ireland': round(eur_price * eurp, 2),
            'uk': round(eur_price * ukp, 2),
            'usa': round(eur_price * usp, 2),
            'canada': round(eur_price * canp, 2),
            'australia': round(eur_price * ausp, 2),
        }

        desc = (
                "<![CDATA["
                "<div style='max-width:680px;margin:0 auto;font-family:Arial,sans-serif;color:#1a1a2e;background:#fff;'>"
                "<div style='background:linear-gradient(135deg,#6b0f1a,#8b1a2a,#a91b2e);padding:28px 32px;'>"
                "<div style='color:#f5c6cb;font-size:13px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;'>MAK Supplies - Professional Grade</div>"
                f"<h1 style='color:#ffffff;font-size:24px;font-weight:700;margin:0 0 10px;line-height:1.3;'>{title}</h1>"
                "<div style='display:inline-block;background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.4);border-radius:4px;padding:5px 14px;color:#ffffff;font-size:13px;font-weight:600;'>ISO Certified &nbsp;|&nbsp; CE Approved &nbsp;|&nbsp; Autoclavable</div>"
                "</div>"
                "<div style='background:#fff0f3;border-left:5px solid #a91b2e;padding:16px 20px;display:table;width:100%;box-sizing:border-box;'>"
                "<div style='display:table-cell;vertical-align:middle;font-size:30px;width:40px;'>&#128207;</div>"
                "<div style='display:table-cell;vertical-align:middle;padding-left:14px;'>"
                "<div style='font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;'>Measurement</div>"
                f"<div style='font-size:24px;font-weight:800;color:#1a1a2e;'>{size}</div>"
                "</div></div>"
                "<div style='padding:20px;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;margin-bottom:10px;border-bottom:2px solid #a91b2e;padding-bottom:6px;'>Specifications</div>"
                "<table style='width:100%;border-collapse:collapse;border:1px solid #e2e8f0;font-size:15px;'>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;width:45%;border-bottom:1px solid #e2e8f0;'>Material</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Premium Surgical Grade Stainless Steel</td></tr>"
                "<tr><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Finishing</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Satin / Matt Finish</td></tr>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Usage</td><td style='padding:11px 14px;border-bottom:1px solid #e2e8f0;'>Reusable</td></tr>"
                "<tr><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;border-bottom:1px solid #e2e8f0;'>Autoclave Safe</td><td style='padding:11px 14px;font-weight:700;color:#15803d;border-bottom:1px solid #e2e8f0;'>Yes - Fully Sterilisable</td></tr>"
                "<tr style='background:#fff0f3;'><td style='padding:11px 14px;font-weight:700;color:#6b0f1a;'>Certifications</td><td style='padding:11px 14px;'>"
                "<span style='background:#6b0f1a;color:#fff;padding:3px 10px;border-radius:4px;font-weight:700;font-size:13px;margin-right:6px;'>ISO</span>"
                "<span style='background:#6b0f1a;color:#fff;padding:3px 10px;border-radius:4px;font-weight:700;font-size:13px;'>CE</span>"
                "</td></tr>"
                "</table>"
                "<div style='margin-top:16px;background:#fff8f8;border-radius:6px;padding:16px;border:1px solid #ffd0d5;font-size:15px;color:#334155;line-height:2;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#a91b2e;margin-bottom:10px;'>Quality Promise</div>"
                "&#10003; Each instrument individually inspected for highest possible quality.<br/>"
                "&#9632; Individually wrapped in protective polythene bag, packed in secure box for safe delivery.<br/>"
                "&#9889; <strong>Dispatched within 24 hours</strong> of cleared payment being received.<br/>"
                "<span style='color:#a91b2e;font-weight:700;'>Buy More, Save More!</span> Combine purchases for a discount - contact us via eBay."
                "</div>"
                "<div style='margin-top:14px;background:#f0fdf4;border-radius:6px;padding:16px;border:1px solid #bbf7d0;font-size:15px;color:#334155;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#15803d;margin-bottom:10px;'>Shipping &amp; Delivery</div>"
                "<table style='width:100%;border-collapse:collapse;font-size:15px;'>"
                "<tr style='background:#dcfce7;'><td style='padding:9px 12px;font-weight:700;color:#15803d;'>Ireland</td><td style='padding:9px 12px;color:#166534;font-weight:600;'>2-3 Business Days</td></tr>"
                "<tr><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>European Union</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>7-15 Business Days</td></tr>"
                "<tr style='background:#f0fdf4;'><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>Rest of Europe</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>10-20 Business Days</td></tr>"
                "<tr><td style='padding:9px 12px;font-weight:600;border-top:1px solid #bbf7d0;'>Worldwide</td><td style='padding:9px 12px;border-top:1px solid #bbf7d0;'>10-26 Business Days</td></tr>"
                "</table>"
                "</div>"
                "<div style='margin-top:14px;background:#fff7ed;border-radius:6px;padding:16px;border:1px solid #fed7aa;font-size:15px;color:#334155;line-height:1.8;'>"
                "<div style='font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#c2410c;margin-bottom:8px;'>Return Policy</div>"
                "Returns accepted within <strong>14 days</strong> of receipt. Items must be in original condition and packaging. Return postage covered by us.<br/>"
                "All items carefully inspected before dispatch. If shipping damage occurs, contact us immediately for a replacement."
                "</div>"
                "</div>"
                "<div style='background:linear-gradient(135deg,#6b0f1a,#8b1a2a,#a91b2e);padding:22px 28px;'>"
                "<div style='font-size:12px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#f5c6cb;margin-bottom:8px;'>About MAK Supplies</div>"
                "<p style='font-size:15px;color:#ffe0e4;margin:0 0 12px;line-height:1.7;'>We specialise in manufacturing surgical, dental, veterinary and manicure instruments. ISO and CE certified. Direct manufacturer offering the highest quality with fast worldwide shipping.</p>"
                "<div style='font-size:14px;color:#fca5a5;'>ISO &amp; CE Certified &nbsp;|&nbsp; Direct Manufacturer &nbsp;|&nbsp; Fast Worldwide Shipping &nbsp;|&nbsp; 14-Day Returns</div>"
                "</div>"
                "</div>"
                "]]>"
        )

        item_specifics = {"NameValueList": [
            {"Name": "Brand", "Value": "MAK"},
            {"Name": "MPN", "Value": sku1},
            {"Name": "TYPE", "Value": "SURGICAL DENTAL MANICURE INSTRUMENTS"},
            {"Name": "Material", "Value": "Stainless Steel"},
            {"Name": "Usage", "Value": "Reuseable"},
            {"Name": "Finishing", "Value": "Satin Finish"},
            {"Name": "Autoclave", "Value": "Yes"},
            {"Name": "Certificate", "Value": "ISO,CE"},
            {"Name": "Country of Origin", "Value": "Ireland"},
            {"Name": "Shipping", "Value": "WorldWide"}
        ]}

        site_config = {
            'ireland': {'currency': 'EUR', 'site_id': '205', 'cur_code': 'euro', 'private': False},
            'uk':      {'currency': 'GBP', 'site_id': '3',   'cur_code': 'gbp',  'private': True},
            'usa':     {'currency': 'USD', 'site_id': '0',   'cur_code': 'usd',  'private': True},
            'canada':  {'currency': 'CAD', 'site_id': '2',   'cur_code': 'cad',  'private': True},
            'australia':{'currency': 'AUD','site_id': '15',  'cur_code': 'aud',  'private': True},
        }

        try:
            from ebaysdk.trading import Connection as Trading
            api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')

            for site in sites:
                cfg = site_config.get(site)
                if not cfg:
                    continue
                item = {
                    "Item": {
                        "Title": title,
                        "Description": desc,
                        "PrimaryCategory": {"CategoryID": cat_id},
                        "Storefront": {"StoreCategoryName": store_cat},
                        "StartPrice": prices[site],
                        "CategoryMappingAllowed": "true",
                        "SKU": sku1,
                        "Country": "IE",
                        "ConditionID": "1000",
                        "Currency": cfg['currency'],
                        "ItemSpecifics": item_specifics,
                        "DispatchTimeMax": "0",
                        "ListingDuration": "GTC",
                        "ListingType": "FixedPriceItem",
                        "ProductListingDetails": {"EAN": "Does not apply"},
                        "PaymentMethods": "PayPal",
                        "PayPalEmailAddress": "3348skt@gmail.com",
                        "PictureDetails": {"PictureURL": photo},
                        "Location": "Dublin, Dublin",
                        "Quantity": qty,
                        "PrivateListing": cfg['private'],
                        "SellerProfiles": {
                            "SellerPaymentProfile": {"PaymentProfileName": "Payment Policy"},
                            "SellerReturnProfile": {"ReturnProfileName": "Return Policy"},
                            "SellerShippingProfile": {"ShippingProfileName": "Free Shipping"}
                        },
                        "SiteId": cfg['site_id']
                    }
                }
                try:
                    if verify_only:
                        res = api.execute('VerifyAddItem', item)
                        apicall = res.dict()
                        fees = apicall.get('Fees', {}).get('Fee', [])
                        results.append({'site': site.upper(), 'status': f'VERIFY OK - Fees: {fees}', 'success': True})
                    else:
                        res = api.execute('AddItem', item)
                        apicall = res.dict()
                        itemid = apicall['ItemID']
                        # Get category name
                        try:
                            cat_res = api.execute('GetCategories', {'CategoryParent': cat_id, 'DetailLevel': 'ReturnAll', 'ViewAllNodes': True})
                            cat_dict = cat_res.dict()
                            category_name = cat_dict['CategoryArray']['Category'][0]['CategoryName']
                        except:
                            category_name = cat_id
                        cursor.execute(
                            "INSERT INTO ebaylisting(catid,category,title,itemid,sku,price,site,currency,chanel,type) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (cat_id, category_name, title, itemid, sku1, prices[site], site, cfg['cur_code'], 'mak', 'single')
                        )
                        results.append({'site': site.upper(), 'itemid': itemid, 'price': prices[site], 'status': 'LISTED ✓', 'success': True})
                except Exception as e:
                    results.append({'site': site.upper(), 'status': str(e), 'success': False})

            if results and not verify_only:
                message = f'Listing complete for SKU {sku1}'
            elif verify_only:
                message = f'Verification complete for SKU {sku1}'

        except Exception as e:
            message = f'API Error: {e}'

    conn.close()
    return render(request, 'dashboard/create_listing.html', {
        'message': message,
        'results': results,
        'sheet_data': sheet_data,
        'step': step,
        'sku_list_keys': sorted(sku_list.keys(), key=lambda x: int(x) if x.isdigit() else 0),
    })

# ============ MANUAL EBAY ORDER IMPORT ============

@staff_member_required
def import_ebay_orders(request):
    results = []
    message = ''
    if request.method == 'POST':
        days = int(request.POST.get('days', 2))
        import subprocess
        try:
            proc = subprocess.run(
                ['/home/maksupplies/.virtualenvs/eshop-env/bin/python',
                 '/home/maksupplies/eshop2/sync_ebay_orders.py'],
                capture_output=True, text=True, timeout=120
            )
            output = proc.stdout + proc.stderr
            lines = [l for l in output.strip().split('\n') if l]
            for line in lines:
                if 'INSERTED' in line:
                    results.append({'line': line, 'type': 'success'})
                elif 'EXISTS' in line:
                    results.append({'line': line, 'type': 'info'})
                elif 'error' in line.lower() or 'Error' in line:
                    results.append({'line': line, 'type': 'danger'})
                else:
                    results.append({'line': line, 'type': 'secondary'})
            inserted = sum(1 for r in results if r['type'] == 'success')
            message = f'Import complete! {inserted} new orders imported.'
        except subprocess.TimeoutExpired:
            message = 'Import timed out after 120 seconds.'
        except Exception as e:
            message = f'Error: {e}'
    return render(request, 'dashboard/import_ebay.html', {
        'results': results,
        'message': message,
    })

# ============ PROFIT REPORTS ============

@staff_member_required
def profit_report(request):
    conn = get_db()
    cursor = conn.cursor()
    report_type = request.GET.get('type', 'monthly')
    year = int(request.GET.get('year', 2025))

    if report_type == 'monthly':
        cursor.execute("""
            SELECT 
                YEAR(time) as yr, MONTH(time) as mn,
                COUNT(*) as orders,
                SUM(quantity) as units,
                SUM(fee) as total_fee,
                SUM(postage) as total_post,
                SUM(cost * quantity) as total_cost,
                AVG(rate) as avg_rate,
                currency,
                SUM(price * quantity + postcharge) as gross
            FROM saleorder
            WHERE YEAR(time) = %s
            GROUP BY YEAR(time), MONTH(time), currency
            ORDER BY yr, mn
        """, (year,))
    else:
        cursor.execute("""
            SELECT 
                YEAR(time) as yr, WEEK(time) as wk,
                COUNT(*) as orders,
                SUM(quantity) as units,
                SUM(fee) as total_fee,
                SUM(postage) as total_post,
                SUM(cost * quantity) as total_cost,
                AVG(rate) as avg_rate,
                currency,
                SUM(price * quantity + postcharge) as gross
            FROM saleorder
            WHERE YEAR(time) = %s
            GROUP BY YEAR(time), WEEK(time), currency
            ORDER BY yr, wk
        """, (year,))

    rows = cursor.fetchall()

    # Group by period and calculate profits
    periods = {}
    for r in rows:
        period = f"{r[0]}-{str(r[1]).zfill(2)}"
        label = ''
        if report_type == 'monthly':
            months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
            label = f"{months[r[1]]} {r[0]}"
        else:
            label = f"Week {r[1]}, {r[0]}"

        if period not in periods:
            periods[period] = {
                'label': label,
                'orders': 0,
                'units': 0,
                'euro': 0,
                'cost': 0,
                'post': 0,
                'fee': 0,
                'profit': 0,
            }

        try:
            quantity = int(r[3] or 0)
            fee = float(r[4] or 0)
            fee2 = 0.43 if r[8] == 'EUR' else 0.36
            fee_total = fee + (fee2 * int(r[2] or 0))
            postage = float(r[5] or 0)
            cost = float(r[6] or 0)
            rate = float(r[7] or 1)
            gross = float(r[9] or 0)
            revenue = gross * rate
            euro = revenue
            profit = euro - cost - postage

            periods[period]['orders'] += int(r[2] or 0)
            periods[period]['units'] += quantity
            periods[period]['euro'] += euro
            periods[period]['cost'] += cost
            periods[period]['post'] += postage
            periods[period]['fee'] += fee_total * rate
            periods[period]['profit'] += profit
        except Exception as e:
            print(f"ROW ERROR: {e}")
            import traceback; traceback.print_exc()
            continue

    # Round values
    report_data = []
    total_orders = total_units = total_euro = total_profit = total_cost = total_post = 0
    for period, d in periods.items():
        euro = round(d['euro'], 2)
        profit = round(d['profit'], 2)
        cost = round(d['cost'], 2)
        post = round(d['post'], 2)
        profit_pct = round((profit / euro * 100), 1) if euro > 0 else 0
        cost_pct = round((cost / euro * 100), 1) if euro > 0 else 0
        post_pct = round((post / euro * 100), 1) if euro > 0 else 0
        report_data.append({
            'label': d['label'],
            'orders': d['orders'],
            'units': d['units'],
            'euro': euro,
            'cost': cost,
            'post': post,
            'fee': round(d['fee'], 2),
            'profit': profit,
            'profit_pct': profit_pct,
            'cost_pct': cost_pct,
            'post_pct': post_pct,
        })
        total_orders += d['orders']
        total_units += d['units']
        total_euro += euro
        total_profit += profit
        total_cost += cost
        total_post += post

    # Get available years
    cursor.execute("SELECT DISTINCT YEAR(time) FROM saleorder ORDER BY YEAR(time) DESC")
    years = [r[0] for r in cursor.fetchall()]
    conn.close()

    return render(request, 'dashboard/profit_report.html', {
        'report_data': report_data,
        'report_type': report_type,
        'year': year,
        'years': years,
        'total_orders': total_orders,
        'total_units': total_units,
        'total_euro': round(total_euro, 2),
        'total_profit': round(total_profit, 2),
        'total_cost': round(total_cost, 2),
        'total_post': round(total_post, 2),
        'profit_pct_avg': round((total_profit / total_euro * 100), 1) if total_euro > 0 else 0,
    })

# ============ SALES VS PURCHASE REPORT ============
@staff_member_required
def sales_vs_purchase(request):
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime, timedelta

    period = request.GET.get('period', '90')
    maker_filter = request.GET.get('maker', '')
    days = int(period)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Get all makers for filter dropdown
    cursor.execute("SELECT name FROM maker ORDER BY name")
    all_makers = [r[0] for r in cursor.fetchall()]

    # Sales data per SKU
    cursor.execute(f"""
        SELECT sku, SUM(quantity) as units_sold, SUM(price*quantity) as revenue
        FROM saleorder
        WHERE time >= %s
        GROUP BY sku
    """, (since,))
    sales_map = {}
    for r in cursor.fetchall():
        sales_map[str(r[0])] = {'units_sold': int(r[1] or 0), 'revenue': float(r[2] or 0)}

    # Purchase data per SKU
    cursor.execute(f"""
        SELECT sku, SUM(qty) as units_ordered, SUM(received_qty) as units_received, SUM(total) as po_value
        FROM purchaseorder
        GROUP BY sku
    """)
    po_map = {}
    for r in cursor.fetchall():
        po_map[str(r[0])] = {
            'units_ordered': int(r[1] or 0),
            'units_received': int(r[2] or 0),
            'po_value': float(r[3] or 0)
        }

    # Inventory data
    if maker_filter:
        cursor.execute("""
            SELECT sku, title, stock, reorder, maker, price, price
            FROM inventory WHERE maker LIKE %s ORDER BY maker, sku*1
        """, (f"%{maker_filter}%",))
    else:
        cursor.execute("""
            SELECT sku, title, stock, reorder, maker, price, price
            FROM inventory ORDER BY maker, sku*1
        """)
    items = cursor.fetchall()

    # Maker ledger summary
    cursor.execute("""
        SELECT maker, SUM(debit) as total_purchased, SUM(credit) as total_paid
        FROM maker_ledger GROUP BY maker
    """)
    ledger_map = {}
    for r in cursor.fetchall():
        ledger_map[r[0]] = {'purchased': float(r[1] or 0), 'paid': float(r[2] or 0)}

    conn.close()

    result = []
    for item in items:
        sku, title, stock, reorder, maker, price, cost = item
        sku_str = str(sku)
        sales = sales_map.get(sku_str, {'units_sold': 0, 'revenue': 0})
        po = po_map.get(sku_str, {'units_ordered': 0, 'units_received': 0, 'po_value': 0})
        price_val = float(price or 0)
        result.append({
            'sku': sku, 'title': title, 'stock': stock, 'reorder': reorder,
            'maker': maker or '', 'price': price_val, 'margin': 0,
            'units_sold': sales['units_sold'], 'revenue': round(sales['revenue'], 0),
            'units_ordered': po['units_ordered'], 'units_received': po['units_received'],
            'po_value': round(po['po_value'], 0),
            'needs_reorder': stock <= (reorder or 0) and (reorder or 0) > 0,
        })

    # Summary stats
    total_revenue = sum(r['revenue'] for r in result)
    total_po_value = sum(r['po_value'] for r in result)
    total_sold = sum(r['units_sold'] for r in result)
    total_ordered = sum(r['units_ordered'] for r in result)
    needs_reorder = sum(1 for r in result if r['needs_reorder'])

    return render(request, 'dashboard/sales_vs_purchase.html', {
        'items': result,
        'all_makers': all_makers,
        'maker_filter': maker_filter,
        'period': period,
        'total_revenue': round(total_revenue, 0),
        'total_po_value': round(total_po_value, 0),
        'total_sold': total_sold,
        'total_ordered': total_ordered,
        'needs_reorder': needs_reorder,
        'ledger_map': ledger_map,
    })

# ============ INVENTORY VALUATION REPORT ============
@staff_member_required
def inventory_valuation(request):
    conn = get_db()
    cursor = conn.cursor()

    maker_filter = request.GET.get('maker', '')
    sort = request.GET.get('sort', 'value')

    # Get all makers
    cursor.execute("SELECT name FROM maker ORDER BY name")
    all_makers = [r[0] for r in cursor.fetchall()]

    if maker_filter:
        cursor.execute("""
            SELECT sku, title, stock, price, profit_margin, maker,
                   polish, packing, freight, cleaning, testing, reorder
            FROM inventory WHERE maker LIKE %s ORDER BY maker, sku*1
        """, (f"%{maker_filter}%",))
    else:
        cursor.execute("""
            SELECT sku, title, stock, price, profit_margin, maker,
                   polish, packing, freight, cleaning, testing, reorder
            FROM inventory ORDER BY maker, sku*1
        """)
    items = cursor.fetchall()
    conn.close()

    from collections import defaultdict
    result = []
    maker_summary = defaultdict(lambda: {'items': 0, 'stock_value': 0, 'sell_value': 0, 'potential_profit': 0})

    for item in items:
        sku, title, stock, price, margin, maker, polish, packing, freight, cleaning, testing, reorder = item
        stock = stock or 0
        price = float(price or 0)
        margin = float(margin or 0)
        maker_key = (maker or 'Unknown').split(',')[0].strip()

        # Cost = price minus profit margin
        cost = round(price * (1 - margin/100), 2) if margin > 0 else price
        stock_value = round(cost * stock, 0)
        sell_value = round(price * stock, 0)
        potential_profit = round((price - cost) * stock, 0)

        result.append({
            'sku': sku, 'title': title, 'stock': stock,
            'price': price, 'cost': cost, 'margin': margin,
            'maker': maker_key,
            'stock_value': stock_value,
            'sell_value': sell_value,
            'potential_profit': potential_profit,
            'needs_reorder': stock <= (reorder or 0) and (reorder or 0) > 0,
        })

        maker_summary[maker_key]['items'] += 1
        maker_summary[maker_key]['stock_value'] += stock_value
        maker_summary[maker_key]['sell_value'] += sell_value
        maker_summary[maker_key]['potential_profit'] += potential_profit

    # Sort
    if sort == 'value':
        result.sort(key=lambda x: x['stock_value'], reverse=True)
    elif sort == 'profit':
        result.sort(key=lambda x: x['potential_profit'], reverse=True)
    elif sort == 'stock':
        result.sort(key=lambda x: x['stock'], reverse=True)
    elif sort == 'margin':
        result.sort(key=lambda x: x['margin'], reverse=True)

    total_stock_value = sum(r['stock_value'] for r in result)
    total_sell_value = sum(r['sell_value'] for r in result)
    total_potential_profit = sum(r['potential_profit'] for r in result)
    total_items = len(result)
    total_units = sum(r['stock'] for r in result)

    maker_summary_list = sorted(maker_summary.items(), key=lambda x: x[1]['stock_value'], reverse=True)

    return render(request, 'dashboard/inventory_valuation.html', {
        'items': result,
        'all_makers': all_makers,
        'maker_filter': maker_filter,
        'sort': sort,
        'total_stock_value': round(total_stock_value, 0),
        'total_sell_value': round(total_sell_value, 0),
        'total_potential_profit': round(total_potential_profit, 0),
        'total_items': total_items,
        'total_units': total_units,
        'maker_summary': maker_summary_list,
    })

# ============ REORDER POINT AUTO-SUGGESTION ============
@staff_member_required
def reorder_suggestions(request):
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime, timedelta
    from collections import defaultdict

    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        updates = data.get('updates', [])
        updated = 0
        for u in updates:
            sku = u.get('sku')
            reorder = int(u.get('reorder', 0))
            cursor.execute("UPDATE inventory SET reorder=%s WHERE sku=%s", (reorder, sku))
            updated += 1
        conn.commit()
        conn.close()
        return JsonResponse({'success': True, 'updated': updated})

    maker_filter = request.GET.get('maker', '')
    lead_days = int(request.GET.get('lead', '30'))

    cursor.execute("SELECT name FROM maker ORDER BY name")
    all_makers = [r[0] for r in cursor.fetchall()]

    now = datetime.now()
    d30  = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    d60  = (now - timedelta(days=60)).strftime('%Y-%m-%d')
    d90  = (now - timedelta(days=90)).strftime('%Y-%m-%d')

    if maker_filter:
        cursor.execute("""
            SELECT sku, title, stock, reorder, maker, price
            FROM inventory WHERE maker LIKE %s ORDER BY maker, sku*1
        """, (f"%{maker_filter}%",))
    else:
        cursor.execute("""
            SELECT sku, title, stock, reorder, maker, price
            FROM inventory ORDER BY maker, sku*1
        """)
    items = cursor.fetchall()

    skus = [str(i[0]) for i in items]
    sales_30 = defaultdict(int)
    sales_60 = defaultdict(int)
    sales_90 = defaultdict(int)

    if skus:
        fmt = ','.join(['%s'] * len(skus))
        cursor.execute(f"SELECT sku, SUM(quantity) FROM saleorder WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku", skus + [d30])
        for sku, qty in cursor.fetchall(): sales_30[str(sku)] = int(qty or 0)
        cursor.execute(f"SELECT sku, SUM(quantity) FROM saleorder WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku", skus + [d60])
        for sku, qty in cursor.fetchall(): sales_60[str(sku)] = int(qty or 0)
        cursor.execute(f"SELECT sku, SUM(quantity) FROM saleorder WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku", skus + [d90])
        for sku, qty in cursor.fetchall(): sales_90[str(sku)] = int(qty or 0)

    conn.close()

    result = []
    for item in items:
        sku, title, stock, reorder, maker, price = item
        sku_str = str(sku)
        s30 = sales_30.get(sku_str, 0)
        s60 = sales_60.get(sku_str, 0)
        s90 = sales_90.get(sku_str, 0)

        daily_rate = s90 / 90 if s90 > 0 else (s60 / 60 if s60 > 0 else (s30 / 30 if s30 > 0 else 0))
        suggested = max(1, round(daily_rate * lead_days)) if daily_rate > 0 else (reorder or 0)
        diff = suggested - (reorder or 0)
        change = 'increase' if diff > 0 else ('decrease' if diff < 0 else 'ok')

        result.append({
            'sku': sku, 'title': title, 'stock': stock or 0,
            'current_reorder': reorder or 0, 'suggested': suggested,
            'maker': (maker or '').split(',')[0].strip(),
            'price': float(price or 0),
            's30': s30, 's60': s60, 's90': s90,
            'daily_rate': round(daily_rate, 2),
            'diff': diff, 'change': change,
        })

    result.sort(key=lambda x: abs(x['diff']), reverse=True)

    increases = sum(1 for r in result if r['change'] == 'increase')
    decreases = sum(1 for r in result if r['change'] == 'decrease')
    no_change = sum(1 for r in result if r['change'] == 'ok')

    return render(request, 'dashboard/reorder_suggestions.html', {
        'items': result,
        'all_makers': all_makers,
        'maker_filter': maker_filter,
        'lead_days': lead_days,
        'increases': increases,
        'decreases': decreases,
        'no_change': no_change,
    })

# ============ LOGOUT ============
def dashboard_logout(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('/managermeriappka/login/?next=/dashboard/')

# ============ SKU INFO ENDPOINT ============
@staff_member_required
def sku_info(request, sku):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, title, stock, price, maker FROM inventory WHERE sku=%s", (sku,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return JsonResponse({'error': f'SKU {sku} not found'})
    return JsonResponse({'sku': row[0], 'title': row[1], 'stock': row[2], 'price': float(row[3] or 0), 'maker': row[4] or ''})

# ============ STOCK MOVEMENT HISTORY ============
@staff_member_required
def stock_movement(request):
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime, timedelta

    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        sku = data.get('sku')
        qty_change = int(data.get('qty_change', 0))
        note = data.get('note', '')
        adj_type = data.get('type', 'adjustment')

        if not sku or qty_change == 0:
            conn.close()
            return JsonResponse({'error': 'Invalid SKU or quantity'})

        cursor.execute("SELECT stock, title FROM inventory WHERE sku=%s", (sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JsonResponse({'error': f'SKU {sku} not found'})

        stock_before = int(row[0] or 0)
        title = row[1] or ''
        stock_after = stock_before + qty_change

        if stock_after < 0:
            conn.close()
            return JsonResponse({'error': f'Stock cannot go below 0. Current stock: {stock_before}'})

        cursor.execute("UPDATE inventory SET stock=%s WHERE sku=%s", (stock_after, sku))
        cursor.execute("""
            INSERT INTO stock_movement (sku, title, date, type, qty_change, stock_before, stock_after, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (sku, title, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), adj_type, qty_change, stock_before, stock_after, note))
        conn.commit()
        conn.close()
        return JsonResponse({'success': True, 'stock_before': stock_before, 'stock_after': stock_after})

    # GET — fetch movement history
    sku_filter = request.GET.get('sku', '')
    type_filter = request.GET.get('type', '')
    days = int(request.GET.get('days', '30'))
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conditions = ["date >= %s"]
    params = [since]

    if sku_filter:
        conditions.append("sku = %s")
        params.append(sku_filter)
    if type_filter:
        conditions.append("type = %s")
        params.append(type_filter)

    where = ' AND '.join(conditions)
    cursor.execute(f"""
        SELECT id, sku, title, date, type, qty_change, stock_before, stock_after, ref, note
        FROM stock_movement WHERE {where}
        ORDER BY date DESC LIMIT 500
    """, params)
    movements = cursor.fetchall()

    # Summary stats
    cursor.execute(f"SELECT SUM(CASE WHEN qty_change > 0 THEN qty_change ELSE 0 END), SUM(CASE WHEN qty_change < 0 THEN ABS(qty_change) ELSE 0 END), COUNT(*) FROM stock_movement WHERE {where}", params)
    stats = cursor.fetchone()
    total_in = int(stats[0] or 0)
    total_out = int(stats[1] or 0)
    total_movements = int(stats[2] or 0)

    conn.close()

    result = []
    for m in movements:
        result.append({
            'id': m[0], 'sku': m[1], 'title': m[2],
            'date': str(m[3]), 'type': m[4],
            'qty_change': m[5], 'stock_before': m[6],
            'stock_after': m[7], 'ref': m[8] or '',
            'note': m[9] or '',
        })

    return render(request, 'dashboard/stock_movement.html', {
        'movements': result,
        'sku_filter': sku_filter,
        'type_filter': type_filter,
        'days': days,
        'total_in': total_in,
        'total_out': total_out,
        'total_movements': total_movements,
    })

# ============ MAKER PERFORMANCE DASHBOARD ============
@staff_member_required
def maker_performance(request):
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime
    from collections import defaultdict

    # Get all makers
    cursor.execute("SELECT id, name, email, mobile FROM maker ORDER BY name")
    all_makers = cursor.fetchall()

    # PO stats per maker
    cursor.execute("""
        SELECT maker,
            COUNT(*) as total_lines,
            SUM(qty) as total_ordered,
            SUM(received_qty) as total_received,
            SUM(CASE WHEN status='received' THEN 1 ELSE 0 END) as fully_received,
            SUM(CASE WHEN status='partial' THEN 1 ELSE 0 END) as partial,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
            AVG(CASE WHEN received_date IS NOT NULL THEN DATEDIFF(received_date, (SELECT MIN(p2.received_date) FROM purchaseorder p2 WHERE p2.porder=purchaseorder.porder AND p2.received_date IS NOT NULL)) ELSE NULL END) as avg_delivery,
            SUM(total) as total_value,
            COUNT(DISTINCT porder) as po_count
        FROM purchaseorder
        GROUP BY maker
    """)
    po_stats = {}
    for r in cursor.fetchall():
        maker = r[0]
        total_ordered = int(r[2] or 0)
        total_received = int(r[3] or 0)
        fulfillment = round((total_received / total_ordered * 100), 1) if total_ordered > 0 else 0
        po_stats[maker] = {
            'total_lines': int(r[1] or 0),
            'total_ordered': total_ordered,
            'total_received': total_received,
            'fully_received': int(r[4] or 0),
            'partial': int(r[5] or 0),
            'pending': int(r[6] or 0),
            'total_value': float(r[8] or 0),
            'po_count': int(r[9] or 0),
            'fulfillment_pct': fulfillment,
        }

    # Ledger balance per maker
    cursor.execute("""
        SELECT maker, SUM(debit) as purchased, SUM(credit) as paid
        FROM maker_ledger GROUP BY maker
    """)
    ledger_stats = {}
    for r in cursor.fetchall():
        ledger_stats[r[0]] = {
            'purchased': float(r[1] or 0),
            'paid': float(r[2] or 0),
            'balance': float(r[1] or 0) - float(r[2] or 0),
        }

    # Item count per maker
    cursor.execute("""
        SELECT maker, COUNT(*) as items, SUM(stock) as total_stock
        FROM inventory GROUP BY maker
    """)
    inv_stats = defaultdict(lambda: {'items': 0, 'total_stock': 0})
    for r in cursor.fetchall():
        maker_key = (r[0] or '').split(',')[0].strip()
        inv_stats[maker_key]['items'] += int(r[1] or 0)
        inv_stats[maker_key]['total_stock'] += int(r[2] or 0)

    conn.close()

    result = []
    for m in all_makers:
        maker_id, name, email, mobile = m
        po = po_stats.get(name, {})
        ledger = ledger_stats.get(name, {'purchased': 0, 'paid': 0, 'balance': 0})
        inv = inv_stats.get(name, {'items': 0, 'total_stock': 0})

        fulfillment = po.get('fulfillment_pct', 0)
        if fulfillment >= 90:
            perf_grade = 'A'
            perf_color = '#16a34a'
        elif fulfillment >= 70:
            perf_grade = 'B'
            perf_color = '#d97706'
        elif fulfillment >= 50:
            perf_grade = 'C'
            perf_color = '#ef4444'
        elif fulfillment > 0:
            perf_grade = 'D'
            perf_color = '#dc2626'
        else:
            perf_grade = '—'
            perf_color = '#94a3b8'

        result.append({
            'id': maker_id,
            'name': name,
            'email': email or '',
            'mobile': mobile or '',
            'items': inv['items'],
            'total_stock': inv['total_stock'],
            'po_count': po.get('po_count', 0),
            'total_ordered': po.get('total_ordered', 0),
            'total_received': po.get('total_received', 0),
            'fully_received': po.get('fully_received', 0),
            'partial': po.get('partial', 0),
            'pending': po.get('pending', 0),
            'fulfillment_pct': fulfillment,
            'total_value': po.get('total_value', 0),
            'balance': ledger['balance'],
            'paid': ledger['paid'],
            'purchased': ledger['purchased'],
            'perf_grade': perf_grade,
            'perf_color': perf_color,
        })

    result.sort(key=lambda x: x['fulfillment_pct'], reverse=True)

    total_makers = len(result)
    total_pos = sum(r['po_count'] for r in result)
    total_ordered = sum(r['total_ordered'] for r in result)
    total_received = sum(r['total_received'] for r in result)
    overall_fulfillment = round((total_received / total_ordered * 100), 1) if total_ordered > 0 else 0
    total_outstanding = sum(r['balance'] for r in result if r['balance'] > 0)

    return render(request, 'dashboard/maker_performance.html', {
        'makers': result,
        'total_makers': total_makers,
        'total_pos': total_pos,
        'total_ordered': total_ordered,
        'total_received': total_received,
        'overall_fulfillment': overall_fulfillment,
        'total_outstanding': round(total_outstanding, 0),
    })

# ============ PURCHASE ORDERS FULL CRUD ============

@staff_member_required
def purchase_orders_full(request):
    conn = get_db()
    cursor = conn.cursor()
    search = request.GET.get('q', '')
    maker_filter = request.GET.get('maker', '')

    sql = """SELECT sr, sku, qty, porder, price, item, size, maker
             FROM purchaseorder"""
    conditions = []
    params = []

    if search:
        conditions.append("(sku LIKE %s OR item LIKE %s OR maker LIKE %s)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if maker_filter:
        conditions.append("maker = %s")
        params.append(maker_filter)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY sr DESC"

    cursor.execute(sql, params)
    raw = cursor.fetchall()
    pos = []
    for r in raw:
        pos.append({
            'sr': r[0],
            'sku': r[1],
            'qty': r[2],
            'porder': r[3],
            'price': r[4],
            'item': r[5],
            'size': r[6],
            'maker': r[7],
            'total': round(float(r[2] or 0) * float(r[4] or 0), 0),
        })

    # Totals
    cursor.execute("SELECT SUM(qty*price), SUM(qty), COUNT(*) FROM purchaseorder")
    totals = cursor.fetchone()
    total_value = round(float(totals[0] or 0), 2)
    total_qty = totals[1] or 0
    total_items = totals[2] or 0

    # Makers for filter
    cursor.execute("SELECT DISTINCT maker FROM purchaseorder WHERE maker != '' ORDER BY maker")
    makers = [r[0] for r in cursor.fetchall()]

    # Inventory SKUs for dropdown
    cursor.execute("SELECT sku, title FROM inventory ORDER BY sku*1")
    inventory_skus = cursor.fetchall()

    conn.close()
    return render(request, 'dashboard/purchase_orders_full.html', {
        'pos': pos,
        'search': search,
        'maker_filter': maker_filter,
        'makers': makers,
        'total_value': total_value,
        'total_qty': total_qty,
        'total_items': total_items,
        'inventory_skus': inventory_skus,
    })

@staff_member_required
def add_purchase_order_full(request):
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        sku = request.POST.get('sku')
        qty = request.POST.get('qty')
        porder = request.POST.get('porder')
        price = request.POST.get('price')
        size = request.POST.get('size', '')
        maker = request.POST.get('maker', '')
        # Get item title from inventory
        cursor.execute("SELECT title FROM inventory WHERE sku=%s", (sku,))
        row = cursor.fetchone()
        item = row[0] if row else ''
        cursor.execute("""INSERT INTO purchaseorder (sku,qty,porder,price,item,size,maker)
                         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                       (sku, qty, porder, price, item, size, maker))
        conn.close()
    return redirect('/dashboard/purchase-orders-full/')

@staff_member_required
def edit_purchase_order(request, po_id):
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        qty = request.POST.get('qty')
        porder = request.POST.get('porder')
        price = request.POST.get('price')
        size = request.POST.get('size', '')
        maker = request.POST.get('maker', '')
        cursor.execute("""UPDATE purchaseorder SET qty=%s, porder=%s, price=%s,
                         size=%s, maker=%s WHERE sr=%s""",
                       (qty, porder, price, size, maker, po_id))
        conn.close()
        return redirect('/dashboard/purchase-orders-full/')
    cursor.execute("SELECT sr,sku,qty,porder,price,item,size,maker FROM purchaseorder WHERE sr=%s", (po_id,))
    po = cursor.fetchone()
    cursor.execute("SELECT DISTINCT maker FROM purchaseorder WHERE maker != '' ORDER BY maker")
    makers = [r[0] for r in cursor.fetchall()]
    conn.close()
    return render(request, 'dashboard/edit_purchase_order.html', {'po': po, 'makers': makers})

@staff_member_required
def delete_purchase_order(request, po_id):
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM purchaseorder WHERE sr=%s", (po_id,))
        conn.close()
    return redirect('/dashboard/purchase-orders-full/')

# ============ GLOBAL RATES SETTINGS ============

@staff_member_required
def settings(request):
    conn = get_db()
    cursor = conn.cursor()
    message = ''
    if request.method == 'POST':
        for key in ['pkr_to_eur', 'freight_rate', 'commission', 'profit_margin']:
            val = request.POST.get(key, 0)
            cursor.execute("UPDATE settings SET value=%s WHERE name=%s", (val, key))
        conn.commit()
        message = 'Settings saved!'
    cursor.execute("SELECT name, value FROM settings")
    settings = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    return render(request, 'dashboard/settings.html', {'settings': settings, 'message': message})


def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, value FROM settings")
    s = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    return s

def get_live_rates():
    try:
        import requests
        r = requests.get('https://api.exchangerate-api.com/v4/latest/EUR', timeout=5)
        data = r.json()
        rates = data['rates']
        return {
            'EUR': 1.0,
            'GBP': round(1 / rates['GBP'], 4),
            'USD': round(rates['USD'], 4),
            'CAD': round(rates['CAD'], 4),
            'AUD': round(rates['AUD'], 4),
        }
    except:
        # Fallback to hardcoded rates
        return {'EUR': 1.0, 'GBP': 0.87, 'USD': 1.16, 'CAD': 1.62, 'AUD': 1.74}

def get_postage_cost(country, weight_g):
    if weight_g <= 100:
        return 1.85
    elif weight_g <= 500:
        return 3.50
    else:
        return 3.95


@staff_member_required
def maker_products(request, maker_name):
    conn = get_db()
    cursor = conn.cursor()

    # Always return makers list for autocomplete
    cursor.execute("SELECT name FROM maker ORDER BY name")
    all_makers = [r[0] for r in cursor.fetchall()]

    # If ALL requested, just return makers list for autocomplete
    if maker_name == 'ALL':
        conn.close()
        return JsonResponse({'items': [], 'makers': all_makers})

    # If ALL_MAKERS requested, return every inventory item
    filter_mode = request.GET.get('filter', 'all')
    if maker_name == 'ALL_MAKERS':
        if filter_mode == 'reorder':
            cursor.execute("""
                SELECT sku, title, stock, price, maker
                FROM inventory
                WHERE stock <= reorder AND reorder > 0
                ORDER BY sku*1 ASC
            """)
        else:
            cursor.execute("""
                SELECT sku, title, stock, price, maker
                FROM inventory
                ORDER BY sku*1 ASC
            """)
        items = cursor.fetchall()
    else:
        # Filter by maker with optional reorder filter
        if filter_mode == 'reorder':
            cursor.execute("""
                SELECT i.sku, i.title, i.stock, i.price, i.maker
                FROM inventory i
                WHERE i.maker LIKE %s AND i.stock <= i.reorder AND i.reorder > 0
                ORDER BY i.sku*1 ASC
            """, (f"%{maker_name}%",))
        else:
            cursor.execute("""
                SELECT i.sku, i.title, i.stock, i.price, i.maker
                FROM inventory i
                WHERE i.maker LIKE %s
                ORDER BY i.sku*1 ASC
            """, (f"%{maker_name}%",))
        items = cursor.fetchall()

    # Get all maker prices for these skus
    sku_list = [str(item[0]) for item in items]
    maker_prices = {}  # {sku: [{name, price}]}
    if sku_list:
        fmt = ','.join(['%s'] * len(sku_list))
        cursor.execute(f"""
            SELECT sku, makername, MAX(price) as price FROM price
            WHERE sku IN ({fmt})
            GROUP BY sku, makername
            ORDER BY sku, makername
        """, sku_list)
        for row in cursor.fetchall():
            s = str(row[0])
            if s not in maker_prices:
                maker_prices[s] = []
            if row[1]:
                maker_prices[s].append({'name': row[1], 'price': float(row[2])})
            else:
                # no maker name — store as default price only
                if s not in maker_prices or not maker_prices[s]:
                    maker_prices[s] = [{'name': '', 'price': float(row[2])}]

    result = []
    for item in items:
        sku, title, stock, inv_price, maker = item
        sku_str = str(sku)
        # Get makers for this sku
        makers_list = maker_prices.get(sku_str, [])
        if not makers_list:
            # fallback to inventory maker field split
            raw = [m.strip() for m in (maker or '').split(',') if m.strip()]
            makers_list = [{'name': m, 'price': float(inv_price or 0)} for m in raw] if raw else [{'name': maker or '', 'price': float(inv_price or 0)}]
        # default price = first maker price
        default_price = makers_list[0]['price'] if makers_list else float(inv_price or 0)
        result.append({
            'sku': sku,
            'title': title,
            'stock': stock,
            'price': default_price,
            'maker': makers_list[0]['name'] if makers_list else (maker or ''),
            'makers': makers_list,
        })

    conn.close()
    return JsonResponse({'items': result, 'makers': all_makers})

def sku_info(request, sku):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, title, price, stock, maker, reorder FROM inventory WHERE sku=%s", (sku,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        return JsonResponse({'error': f'SKU {sku} not found'})
    # Get all makers and prices from price table
    cursor.execute("SELECT makername, MAX(price) as price FROM price WHERE sku=%s GROUP BY makername ORDER BY makername", (sku,))
    price_rows = cursor.fetchall()
    conn.close()
    # Build makers list from price table, fallback to inventory maker field
    if price_rows:
        makers = [{'name': row[0], 'price': float(row[1])} for row in price_rows]
    else:
        # Split comma separated makers from inventory
        raw_makers = [m.strip() for m in (r[4] or '').split(',') if m.strip()]
        makers = [{'name': m, 'price': float(r[2] or 0)} for m in raw_makers] if raw_makers else [{'name': r[4] or '', 'price': float(r[2] or 0)}]
    return JsonResponse({
        'sku': r[0],
        'title': r[1],
        'price': float(r[2] or 0),
        'stock': r[3],
        'maker': r[4] or '',
        'reorder': r[5] or 0,
        'makers': makers,
    })

@staff_member_required
def save_purchase_order(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        po_number = data['po_number']
        lines = data['lines']
        conn = get_db()
        cursor = conn.cursor()
        for line in lines:
            cursor.execute(
                "INSERT INTO purchaseorder (sku, qty, porder, price, item, size, maker) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (line['sku'], line['qty'], po_number, line['price'], line['title'], line['size'], line['maker'])
            )
        conn.commit()
        conn.close()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Invalid request'})

# ============ EMAIL PO TO MAKER ============
@staff_member_required
def email_po(request):
    if request.method == 'POST':
        import json
        from django.core.mail import EmailMessage
        from datetime import date
        data = json.loads(request.body)
        po_number = data.get('po_number')
        maker_name = data.get('maker')
        extra_note = data.get('note', '')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT email, name, mobile FROM maker WHERE name=%s", (maker_name,))
        maker_row = cursor.fetchone()
        if not maker_row or not maker_row[0]:
            conn.close()
            return JsonResponse({'error': f'No email found for {maker_name}. Please add email in Makers page.'})

        maker_email = maker_row[0]

        cursor.execute("""
            SELECT sku, item, qty, price, size, (qty*price) as total
            FROM purchaseorder WHERE porder=%s AND maker=%s ORDER BY sr
        """, (po_number, maker_name))
        lines = cursor.fetchall()
        conn.close()

        if not lines:
            return JsonResponse({'error': 'No lines found for this PO'})

        today = date.today().strftime('%d %b %Y')
        grand_total = sum(float(l[5] or 0) for l in lines)

        rows = ''
        for l in lines:
            rows += (
                '<tr>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;">' + str(l[0]) + '</td>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;">' + str(l[1]) + '</td>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">' + str(l[4] or '-') + '</td>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">' + str(l[2]) + '</td>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;">' + str(int(l[3] or 0)) + '</td>'
                '<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:700;">' + str(int(l[5] or 0)) + '</td>'
                '</tr>'
            )

        note_html = ('<p style="margin:16px 0;padding:12px 16px;background:#fff9c4;border-left:4px solid #f59e0b;border-radius:4px;">' + extra_note + '</p>') if extra_note else ''

        html = (
            '<div style="max-width:700px;margin:0 auto;font-family:Arial,sans-serif;color:#1a1a2e;">'
            '<div style="background:linear-gradient(135deg,#6b0f1a,#a91b2e);padding:24px 28px;border-radius:12px 12px 0 0;">'
            '<h2 style="margin:0;color:white;font-size:20px;">Purchase Order #' + str(po_number) + '</h2>'
            '<p style="margin:6px 0 0;color:#f5c6cb;font-size:13px;">MAK Supplies — ' + today + '</p>'
            '</div>'
            '<div style="background:#f8fafc;padding:20px 28px;border:1px solid #e2e8f0;border-top:none;">'
            '<p style="margin:0;font-size:14px;">Dear <strong>' + maker_name + '</strong>,</p>'
            '<p style="margin:12px 0;font-size:14px;color:#475569;">Please find below our purchase order. Kindly confirm receipt and expected delivery date.</p>'
            + note_html +
            '</div>'
            '<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-top:none;">'
            '<thead><tr style="background:#1e293b;">'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:left;">SKU</th>'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:left;">Description</th>'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:center;">Size</th>'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:center;">Qty</th>'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:right;">Price (PKR)</th>'
            '<th style="padding:10px 12px;color:white;font-size:12px;text-align:right;">Total (PKR)</th>'
            '</tr></thead>'
            '<tbody>' + rows + '</tbody>'
            '<tfoot><tr style="background:#fef2f2;">'
            '<td colspan="5" style="padding:12px;text-align:right;font-weight:800;font-size:15px;">Grand Total:</td>'
            '<td style="padding:12px;text-align:right;font-weight:800;font-size:15px;color:#a91b2e;">PKR ' + str(int(grand_total)) + '</td>'
            '</tr></tfoot>'
            '</table>'
            '<div style="padding:20px 28px;background:#f8fafc;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;">'
            '<p style="margin:0;font-size:13px;color:#64748b;">Please reply to this email to confirm your order.</p>'
            '<p style="margin:8px 0 0;font-size:13px;color:#64748b;"><strong>MAK Supplies</strong> | 3348skt@gmail.com</p>'
            '</div></div>'
        )

        try:
            from django.core.mail import EmailMessage
            email_msg = EmailMessage(
                subject='Purchase Order #' + str(po_number) + ' — MAK Supplies',
                body=html,
                from_email='MAK Supplies <3348skt@gmail.com>',
                to=[maker_email],
                reply_to=['3348skt@gmail.com'],
            )
            email_msg.content_subtype = 'html'
            email_msg.send()
            return JsonResponse({'success': True, 'sent_to': maker_email})
        except Exception as e:
            return JsonResponse({'error': str(e)})

    return JsonResponse({'error': 'Invalid method'})

# ============ RECEIVE PURCHASE ORDER ============
@staff_member_required
def receive_po(request):
    if request.method == 'GET':
        po_number = request.GET.get('po')
        if not po_number:
            return JsonResponse({'error': 'No PO number provided'})
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sr, sku, item, maker, qty, received_qty, price, size, status
            FROM purchaseorder WHERE porder = %s ORDER BY sr
        """, (po_number,))
        rows = cursor.fetchall()
        conn.close()
        lines = []
        for r in rows:
            lines.append({
                'sr': r[0], 'sku': r[1], 'title': r[2], 'maker': r[3],
                'ordered_qty': r[4], 'received_qty': r[5] or 0,
                'price': float(r[6] or 0), 'size': r[7], 'status': r[8],
                'outstanding': (r[4] or 0) - (r[5] or 0),
            })
        return JsonResponse({'lines': lines, 'po_number': po_number})

    elif request.method == 'POST':
        import json
        from datetime import date
        data = json.loads(request.body)
        receives = data.get('receives', [])
        conn = get_db()
        cursor = conn.cursor()
        today = date.today().strftime('%Y-%m-%d')
        updated = 0
        for item in receives:
            sr = item.get('sr')
            recv_qty = int(item.get('received_qty', 0))
            if recv_qty <= 0:
                continue
            # Get current state
            cursor.execute("SELECT sku, qty, received_qty FROM purchaseorder WHERE sr=%s", (sr,))
            row = cursor.fetchone()
            if not row:
                continue
            sku, ordered_qty, already_received = row
            already_received = already_received or 0
            new_received = already_received + recv_qty
            # Determine status
            if new_received >= ordered_qty:
                status = 'received'
            else:
                status = 'partial'
            # Update purchaseorder line
            cursor.execute("""
                UPDATE purchaseorder
                SET received_qty=%s, received_date=%s, status=%s
                WHERE sr=%s
            """, (new_received, today, status, sr))
            # Get stock before update
            cursor.execute("SELECT stock, title FROM inventory WHERE sku=%s", (sku,))
            inv_row = cursor.fetchone()
            stock_before = int(inv_row[0] or 0) if inv_row else 0
            item_title = inv_row[1] if inv_row else ''
            stock_after = stock_before + recv_qty

            # Add stock to inventory
            cursor.execute("UPDATE inventory SET stock = stock + %s WHERE sku=%s", (recv_qty, sku))

            # Log stock movement
            cursor.execute("""
                INSERT INTO stock_movement (sku, title, date, type, qty_change, stock_before, stock_after, ref, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (sku, item_title, today, 'received', recv_qty, stock_before, stock_after, f'PO-{sr}', f'Received from PO #{sr}'))

            # Add ledger entry for this maker
            cursor.execute("SELECT item, price, maker FROM purchaseorder WHERE sr=%s", (sr,))
            po_row = cursor.fetchone()
            if po_row:
                item_title, price, maker = po_row
                debit_amount = round(float(price or 0) * recv_qty, 0)
                po_ref = str(data.get('po_number', ''))
                # Get current balance for this maker
                cursor.execute("SELECT balance FROM maker_ledger WHERE maker=%s ORDER BY id DESC LIMIT 1", (maker,))
                bal_row = cursor.fetchone()
                current_balance = float(bal_row[0]) if bal_row else 0.0
                new_balance = current_balance + debit_amount
                cursor.execute("""
                    INSERT INTO maker_ledger (maker, date, type, description, debit, credit, balance, ref)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (maker, today, 'purchase', f'Received {recv_qty} x {item_title}', debit_amount, 0, new_balance, f'PO-{sr}'))
            updated += 1
        conn.commit()
        conn.close()
        return JsonResponse({'success': True, 'updated': updated})

    return JsonResponse({'error': 'Invalid method'})

# ============ MAKER LEDGER ============
@staff_member_required
def maker_ledger(request, maker_name):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        # Add manual payment
        import json
        from datetime import date
        data = json.loads(request.body)
        amount = float(data.get('amount', 0))
        description = data.get('description', 'Payment')
        pay_date = data.get('date', date.today().strftime('%Y-%m-%d'))
        ref = data.get('ref', '')
        pay_type = data.get('type', 'payment')

        if amount <= 0:
            conn.close()
            return JsonResponse({'error': 'Invalid amount'})

        cursor.execute("SELECT balance FROM maker_ledger WHERE maker=%s ORDER BY id DESC LIMIT 1", (maker_name,))
        bal_row = cursor.fetchone()
        current_balance = float(bal_row[0]) if bal_row else 0.0

        if pay_type == 'advance':
            new_balance = current_balance - amount
            cursor.execute("""
                INSERT INTO maker_ledger (maker, date, type, description, debit, credit, balance, ref)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (maker_name, pay_date, 'advance', description, 0, amount, new_balance, ref))
        else:
            new_balance = current_balance - amount
            cursor.execute("""
                INSERT INTO maker_ledger (maker, date, type, description, debit, credit, balance, ref)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (maker_name, pay_date, 'payment', description, 0, amount, new_balance, ref))

        conn.commit()
        conn.close()
        return JsonResponse({'success': True, 'new_balance': new_balance})

    # GET — fetch ledger entries
    cursor.execute("""
        SELECT id, date, type, description, debit, credit, balance, ref
        FROM maker_ledger WHERE maker=%s ORDER BY id ASC
    """, (maker_name,))
    entries = cursor.fetchall()

    # Get maker info
    cursor.execute("SELECT id, name, address, mobile, landline FROM maker WHERE name=%s", (maker_name,))
    maker_row = cursor.fetchone()

    # Summary
    cursor.execute("SELECT SUM(debit), SUM(credit) FROM maker_ledger WHERE maker=%s", (maker_name,))
    totals = cursor.fetchone()
    total_debit = float(totals[0] or 0)
    total_credit = float(totals[1] or 0)
    balance = total_debit - total_credit

    conn.close()
    ledger = []
    for e in entries:
        ledger.append({
            'id': e[0], 'date': str(e[1]), 'type': e[2],
            'description': e[3], 'debit': float(e[4] or 0),
            'credit': float(e[5] or 0), 'balance': float(e[6] or 0),
            'ref': e[7] or '',
        })

    from datetime import date
    return render(request, 'dashboard/maker_ledger.html', {
        'maker_name': maker_name,
        'maker': maker_row,
        'ledger': ledger,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance': balance,
        'today': date.today().strftime('%Y-%m-%d'),
    })

# ============ PUSH TO EBAY ============
@staff_member_required
def push_to_ebay(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        stock = int(data.get('stock', 0))
        prices = data.get('prices', {})

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT sku FROM inventory WHERE serial=%s", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return JsonResponse({'success': False, 'error': 'SKU not found'})

        sku = row[0]
        results = []

        try:
            from ebaysdk.trading import Connection as Trading
            api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')

            cursor.execute("SELECT itemid, site FROM ebaylisting WHERE sku=%s", (sku,))
            listings = cursor.fetchall()

            for itemid, site in listings:
                site_key = (site or '').lower()
                price = prices.get(site_key)
                try:
                    item_data = {'ItemID': itemid, 'Quantity': stock}
                    if price:
                        item_data['StartPrice'] = str(price)
                    api.execute('ReviseFixedPriceItem', {'Item': item_data})
                    if price:
                        cursor.execute("UPDATE ebaylisting SET price=%s WHERE itemid=%s", (price, itemid))
                    results.append({'site': site.upper(), 'status': f'Stock={stock} Price={price}', 'success': True})
                except Exception as e:
                    results.append({'site': site.upper(), 'status': str(e)[:80], 'success': False})

            # Update eshop product stock
            try:
                cursor.execute("UPDATE products_product SET stock=%s WHERE sku=%s", (stock, sku))
            except:
                pass

            conn.commit()
            conn.close()
            return JsonResponse({'success': True, 'results': results})

        except Exception as e:
            conn.close()
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid method'})

# ============ AUTO PO FROM LOW STOCK ============
@staff_member_required
def low_stock_po(request):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'GET':
        from datetime import datetime, timedelta
        from collections import defaultdict

        filter_mode = request.GET.get('filter', 'reorder')

        # Return items grouped by maker — filter controls which items
        if filter_mode == 'all':
            cursor.execute("""
                SELECT sku, title, stock, reorder, maker, price
                FROM inventory
                ORDER BY maker, sku*1
            """)
        else:
            cursor.execute("""
                SELECT sku, title, stock, reorder, maker, price
                FROM inventory
                WHERE stock <= reorder AND reorder > 0
                ORDER BY maker, sku*1
            """)
        items = cursor.fetchall()

        # Get sales history for all SKUs in last 90 days
        now = datetime.now()
        d30 = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        d60 = (now - timedelta(days=60)).strftime('%Y-%m-%d')
        d90 = (now - timedelta(days=90)).strftime('%Y-%m-%d')

        skus = [str(i[0]) for i in items]
        sales_30 = defaultdict(int)
        sales_60 = defaultdict(int)
        sales_90 = defaultdict(int)

        if skus:
            fmt = ','.join(['%s'] * len(skus))
            cursor.execute(f"""SELECT sku, SUM(quantity) FROM saleorder
                WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku""", skus + [d30])
            for sku, qty in cursor.fetchall():
                sales_30[str(sku)] = int(qty or 0)

            cursor.execute(f"""SELECT sku, SUM(quantity) FROM saleorder
                WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku""", skus + [d60])
            for sku, qty in cursor.fetchall():
                sales_60[str(sku)] = int(qty or 0)

            cursor.execute(f"""SELECT sku, SUM(quantity) FROM saleorder
                WHERE sku IN ({fmt}) AND time >= %s GROUP BY sku""", skus + [d90])
            for sku, qty in cursor.fetchall():
                sales_90[str(sku)] = int(qty or 0)

        # Get next PO number
        cursor.execute("SELECT MAX(porder) FROM purchaseorder")
        max_po = cursor.fetchone()[0] or 25000
        next_po = int(max_po) + 1

        makers = defaultdict(list)
        for sku, title, stock, reorder, maker, price in items:
            maker_key = maker.split(',')[0].strip() if maker else 'Unknown'
            s30 = sales_30.get(str(sku), 0)
            s60 = sales_60.get(str(sku), 0)
            s90 = sales_90.get(str(sku), 0)

            # Suggested qty: based on 90-day velocity + buffer
            daily_rate = s90 / 90 if s90 > 0 else 0
            suggested = max(
                (reorder or 0) - (stock or 0),  # at minimum fill to reorder
                round(daily_rate * 60)           # or 60 days of stock
            )
            suggested = max(1, suggested)

            makers[maker_key].append({
                'sku': sku,
                'title': title,
                'stock': stock,
                'reorder': reorder,
                'qty': suggested,
                'price': float(price or 0),
                'total': float(price or 0) * suggested,
                's30': s30,
                's60': s60,
                's90': s90,
                'suggested': suggested,
            })

        result = []
        po_num = next_po
        for maker, items_list in sorted(makers.items()):
            grand = sum(i['total'] for i in items_list)
            result.append({
                'maker': maker,
                'po_number': po_num,
                'items': items_list,
                'total': round(grand, 0),
                'count': len(items_list),
            })
            po_num += 1

        conn.close()
        return JsonResponse({'groups': result, 'next_po': next_po})

    elif request.method == 'POST':
        import json
        data = json.loads(request.body)
        groups = data.get('groups', [])

        cursor.execute("SELECT MAX(porder) FROM purchaseorder")
        max_po = cursor.fetchone()[0] or 25000
        po_num = int(max_po) + 1

        saved = 0
        from datetime import datetime
        batch_id = 'B' + datetime.now().strftime('%Y%m%d%H%M')
        for group in groups:
            maker = group.get('maker', '')
            for item in group.get('items', []):
                if item.get('removed'): continue
                sku = item.get('sku')
                qty = int(item.get('qty', 1))
                price = float(item.get('price', 0))
                title = item.get('title', '')
                stock = item.get('stock', 0)
                total = round(price * qty, 0)
                cursor.execute("""
                    INSERT INTO purchaseorder (sku, porder, qty, price, item, size, maker, stock, total, batch_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (sku, po_num, qty, price, title, '', maker, stock, total, batch_id))
                saved += 1
            po_num += 1

        conn.commit()
        conn.close()
        return JsonResponse({'success': True, 'saved': saved, 'pos_created': po_num - (int(max_po) + 1), 'batch_id': batch_id})

    conn.close()
    return JsonResponse({'error': 'Invalid method'})

# ============ THERMAL LABEL PDF ============

@staff_member_required
def thermal_label_pdf(request):
    from reportlab.lib.pagesizes import mm
    from reportlab.pdfgen import canvas
    ids = request.GET.get('ids', '').split(',')
    ids = [i.strip() for i in ids if i.strip()]
    if not ids:
        return HttpResponse('No orders selected', status=400)

    conn = get_db()
    cursor = conn.cursor()
    fmt = ','.join(['%s'] * len(ids))
    cursor.execute(f"""SELECT name, street1, street2, city, state, postcode, country, phone
                       FROM saleorder WHERE id IN ({fmt})""", ids)
    orders = cursor.fetchall()
    conn.close()

    # 50x50mm page
    W = 50 * mm
    H = 50 * mm

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="labels.pdf"'

    c = canvas.Canvas(response, pagesize=(W, H))
    c.setPageSize((W, H))

    for o in orders:
        name     = (o[0] or '').strip()
        street1  = (o[1] or '').strip()
        street2  = (o[2] or '').strip()
        city     = (o[3] or '').strip()
        state    = (o[4] or '').strip()
        postcode = (o[5] or '').strip()
        country  = (o[6] or '').upper().strip()
        phone    = (o[7] or '').strip()

        city_line = ', '.join(filter(None, [city, state, postcode]))

        y = H - 3*mm
        LINE = 4.5*mm

        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(W/2, y, name)
        y -= LINE

        if street1:
            c.setFont('Helvetica-Bold', 10)
            c.drawCentredString(W/2, y, street1)
            y -= LINE

        if street2:
            c.setFont('Helvetica-Bold', 10)
            c.drawCentredString(W/2, y, street2)
            y -= LINE

        if city_line:
            c.setFont('Helvetica-Bold', 10)
            c.drawCentredString(W/2, y, city_line)
            y -= LINE

        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(W/2, y, country)
        y -= LINE

        if phone:
            c.setFont('Helvetica-Bold', 10)
            c.drawCentredString(W/2, y, u'☎ ' + phone)

        c.showPage()

    c.save()
    return response

# ============ THERMAL LABEL PNG ============
@staff_member_required
def thermal_label_png(request):
    from PIL import Image, ImageDraw, ImageFont
    import io, zipfile
    ids = request.GET.get('ids', '').split(',')
    ids = [i.strip() for i in ids if i.strip()]
    if not ids:
        return HttpResponse('No orders selected', status=400)
    conn = get_db()
    cursor = conn.cursor()
    fmt = ','.join(['%s'] * len(ids))
    cursor.execute(f"""SELECT name, street1, street2, city, state, postcode, country, phone
                       FROM saleorder WHERE id IN ({fmt})""", ids)
    orders = cursor.fetchall()
    conn.close()

    DPI = 300
    W = int(50 / 25.4 * DPI)
    H = int(50 / 25.4 * DPI)

    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 36)
        font_country = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 44)
    except:
        font = ImageFont.load_default()
        font_country = font

    images = []
    for o in orders:
        name      = (o[0] or '').strip()
        street1   = (o[1] or '').strip()
        street2   = (o[2] or '').strip()
        city      = (o[3] or '').strip()
        state     = (o[4] or '').strip()
        postcode  = (o[5] or '').strip()
        country   = (o[6] or '').upper().strip()
        phone     = (o[7] or '').strip()
        city_line = ', '.join(filter(None, [city, state, postcode]))

        img = Image.new('RGB', (W, H), color='white')
        draw = ImageDraw.Draw(img)

        lines = []
        if name:      lines.append((name, font))
        if street1:   lines.append((street1, font))
        if street2:   lines.append((street2, font))
        if city_line: lines.append((city_line, font))
        if country:   lines.append((country, font_country))
        if phone:     lines.append((u'\u260e ' + phone, font))

        LINE_GAP = 12
        total_h = sum(f.getbbox(t)[3] + LINE_GAP for t, f in lines)
        y = (H - total_h) // 2

        for text, f in lines:
            bbox = f.getbbox(text)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            draw.text((x, y), text, font=f, fill='black')
            y += bbox[3] + LINE_GAP

        images.append(img)

    if len(images) == 1:
        buf = io.BytesIO()
        images[0].save(buf, format='PNG', dpi=(DPI, DPI))
        buf.seek(0)
        response = HttpResponse(buf, content_type='image/png')
        response['Content-Disposition'] = 'attachment; filename="label.png"; filename*=UTF-8\'\'label.png'
        return response
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for i, img in enumerate(images):
                ibuf = io.BytesIO()
                img.save(ibuf, format='PNG', dpi=(DPI, DPI))
                zf.writestr(f'label_{i+1}.png', ibuf.getvalue())
        buf.seek(0)
        response = HttpResponse(buf, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="labels.zip"'
        return response

# =================================================================
# BULK OPERATIONS & EXTERNAL SYNC
# =================================================================

@staff_member_required
def upload_to_eshop(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        created = 0
        updated = 0
        errors = []
        total = 0
        try:
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string)
            rows = list(reader)
            total = len(rows)
            store, _ = Store.objects.get_or_create(name="Main Store")
            for i, row in enumerate(rows):
                try:
                    sku = (row.get('SKU') or row.get('sku') or '').strip()
                    if not sku:
                        errors.append(f'Row {i+1}: Missing SKU')
                        continue
                    category, _ = Category.objects.get_or_create(
                        name=row.get('category', 'General').strip()
                    )
                    subcategory = None
                    if row.get('subcategory', '').strip():
                        subcategory, _ = SubCategory.objects.get_or_create(
                            name=row['subcategory'].strip(),
                            category=category
                        )
                    obj, was_created = Product.objects.update_or_create(
                        sku=sku,
                        defaults={
                            'name': row.get('name', 'Unnamed Product').strip(),
                            'description': row.get('description', '').strip(),
                            'price': float(row.get('price') or 0),
                            'stock': int(float(row.get('stock') or 0)),
                            'category': category,
                            'subcategory': subcategory,
                            'store': store,
                            'image': row.get('image', '').strip() or 'products/default.jpg'
                        }
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors.append(f'Row {i+1} SKU {row.get("SKU","?")}: {str(e)}')
        except Exception as e:
            errors.append(f'File error: {str(e)}')

        from django.contrib import messages
        messages.success(request, f'E-Shop Sync Complete — {total} rows: {created} created, {updated} updated.')
        request.session['eshop_sync_errors'] = errors[:50]
        request.session['eshop_sync_stats'] = {'total': total, 'created': created, 'updated': updated}
    return redirect('dashboard:inventory')



@staff_member_required
def combined_profit_report(request):
    import json
    from collections import defaultdict
    from django.http import JsonResponse

    conn = get_db()
    cursor = conn.cursor()

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    source_filter = request.GET.get('source', 'all')
    sort_by = request.GET.get('sort', 'date')
    sort_dir = request.GET.get('dir', 'desc')

    # Handle inline cost edit (AJAX POST)
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        data = json.loads(request.body)
        row_id = data.get('id')
        source = data.get('source')
        field = data.get('field')
        value = float(data.get('value', 0))
        if source == 'ebay' and field == 'postage':
            cursor.execute("UPDATE saleorder SET postage=%s WHERE id=%s", (value, row_id))
        elif source == 'ebay' and field == 'fee':
            cursor.execute("UPDATE saleorder SET fee=%s WHERE id=%s", (value, row_id))
        conn.close()
        return JsonResponse({'ok': True})

    ebay_where = ["IFNULL(s.site,'') != 'eshop'" ]
    eshop_where = ["o.paid=1"]
    params_ebay = []
    params_eshop = []

    if date_from:
        ebay_where.append("DATE(s.time) >= %s")
        params_ebay.append(date_from)
        eshop_where.append("DATE(o.created_at) >= %s")
        params_eshop.append(date_from)
    if date_to:
        ebay_where.append("DATE(s.time) <= %s")
        params_ebay.append(date_to)
        eshop_where.append("DATE(o.created_at) <= %s")
        params_eshop.append(date_to)

    rows = []

    # Get PKR to EUR rate
    cursor.execute("SELECT value FROM settings WHERE name='pkr_to_eur'")
    row = cursor.fetchone()
    PKR_EUR = float(row[0]) if row else 180.0

    if source_filter in ('all', 'ebay'):
        ebay_sql = f"""
            SELECT s.id, s.orderid, s.name, s.country, s.time, s.sku, i.title,
                s.quantity,
                (s.price * s.quantity + IFNULL(s.postcharge,0)) * IFNULL(s.rate,1) as revenue,
                IFNULL(s.cost,0) as cost_pkr,
                IFNULL(s.postage,0) as postage,
                IFNULL(s.fee,0) * IFNULL(s.rate,1) as fee,
                s.currency, s.site
            FROM saleorder s
            LEFT JOIN inventory i ON i.sku = s.sku
            WHERE {' AND '.join(ebay_where)}
        ORDER BY s.time DESC
        """
        cursor.execute(ebay_sql, params_ebay)
        for r in cursor.fetchall():
            revenue = float(r[8] or 0)
            cost = round(float(r[9] or 0) * int(r[7] or 1), 2)
            postage = float(r[10] or 0)
            fee = float(r[11] or 0)
            profit = revenue - cost - postage - fee
            profit_pct = round((profit / revenue * 100), 1) if revenue > 0 else 0
            rows.append({
                'id': r[0], 'source': 'eBay', 'source_badge': 'ebay',
                'order_ref': r[1] or f'eBay-{r[0]}',
                'customer': r[2] or '—', 'country': r[3] or '—',
                'date': str(r[4])[:10] if r[4] else '—',
                'sku': str(r[5]) if r[5] else '—',
                'product': r[6] or r[1] or '—',
                'qty': int(r[7] or 1),
                'revenue': round(revenue, 2), 'cost': round(cost, 2),
                'postage': round(postage, 2), 'fee': round(fee, 2),
                'profit': round(profit, 2), 'profit_pct': profit_pct,
                'currency': r[12] or 'EUR', 'site': r[13] or '—',
            })

    if source_filter in ('all', 'eshop'):
        eshop_sql = f"""
            SELECT o.id, IFNULL(o.order_number, CONCAT('ESHOP-', o.id)),
                o.full_name,
                JSON_UNQUOTE(JSON_EXTRACT(o.shipping_address, '$.country')),
                o.created_at, oi.sku, oi.product_name, oi.quantity,
                oi.price * oi.quantity as revenue,
                (IFNULL(i.price,0) + IFNULL(i.polish,0) + IFNULL(i.packing,0) + ROUND(IFNULL(i.weight,0) * 1000/1000, 2) + IFNULL(i.cleaning,0) + IFNULL(i.testing,0)) / {PKR_EUR} as cost_eur,
                0, 0, 'GBP', 'eshop'
            FROM orders_order o
            JOIN orders_orderitem oi ON oi.order_id = o.id
            LEFT JOIN inventory i ON i.sku = oi.sku
            WHERE {' AND '.join(eshop_where)}
        """
        cursor.execute(eshop_sql, params_eshop)
        for r in cursor.fetchall():
            revenue = float(r[8] or 0)
            cost = round(float(r[9] or 0) * int(r[7] or 1), 2)
            profit = revenue - cost
            profit_pct = round((profit / revenue * 100), 1) if revenue > 0 else 0
            rows.append({
                'id': r[0], 'source': 'Eshop', 'source_badge': 'eshop',
                'order_ref': r[1] or f'ESHOP-{r[0]}',
                'customer': r[2] or '—', 'country': r[3] or '—',
                'date': str(r[4])[:10] if r[4] else '—',
                'sku': str(r[5]) if r[5] else '—',
                'product': r[6] or '—',
                'qty': int(r[7] or 1),
                'revenue': round(revenue, 2), 'cost': round(cost, 2),
                'postage': 0, 'fee': 0,
                'profit': round(profit, 2), 'profit_pct': profit_pct,
                'currency': 'GBP', 'site': 'eshop',
            })

    sort_map = {'date': 'date', 'revenue': 'revenue', 'profit': 'profit',
                'profit_pct': 'profit_pct', 'cost': 'cost', 'customer': 'customer'}
    rows.sort(key=lambda x: x[sort_map.get(sort_by, 'date')], reverse=(sort_dir == 'desc'))

    total_revenue = sum(r['revenue'] for r in rows)
    total_cost = sum(r['cost'] for r in rows)
    total_postage = sum(r['postage'] for r in rows)
    total_fee = sum(r['fee'] for r in rows)
    total_profit = sum(r['profit'] for r in rows)
    total_orders = len(set(r['order_ref'] for r in rows))
    total_units = sum(r['qty'] for r in rows)
    profit_pct_avg = round((total_profit / total_revenue * 100), 1) if total_revenue > 0 else 0

    chart_data = defaultdict(lambda: {'revenue': 0, 'profit': 0, 'cost': 0})
    for r in rows:
        d = r['date'][:7] if r['date'] != '—' else 'Unknown'
        chart_data[d]['revenue'] += r['revenue']
        chart_data[d]['profit'] += r['profit']
        chart_data[d]['cost'] += r['cost']
    chart_labels = sorted(chart_data.keys())
    chart_revenue = [round(chart_data[k]['revenue'], 2) for k in chart_labels]
    chart_profit = [round(chart_data[k]['profit'], 2) for k in chart_labels]
    chart_cost = [round(chart_data[k]['cost'], 2) for k in chart_labels]

    conn.close()

    return render(request, 'dashboard/combined_profit_report.html', {
        'rows': rows,
        'total_revenue': round(total_revenue, 2),
        'total_cost': round(total_cost, 2),
        'total_postage': round(total_postage, 2),
        'total_fee': round(total_fee, 2),
        'total_profit': round(total_profit, 2),
        'total_orders': total_orders,
        'total_units': total_units,
        'profit_pct_avg': profit_pct_avg,
        'date_from': date_from,
        'date_to': date_to,
        'source_filter': source_filter,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'chart_labels': chart_labels,
        'chart_revenue': chart_revenue,
        'chart_profit': chart_profit,
        'chart_cost': chart_cost,
        'row_count': len(rows),
    })

# ============ BULK ESHOP PRICE SYNC ============

@staff_member_required
def sync_prices_to_eshop(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'})
    conn = get_db()
    cursor = conn.cursor()
    s = get_settings()
    PKR_EUR = float(s.get('pkr_to_eur', 180))
    FREIGHT_RATE = float(s.get('freight_rate', 1000))
    COMMISSION = float(s.get('commission', 25)) / 100
    DEFAULT_PROFIT = 1 + float(s.get('profit_margin', 75)) / 100

    cursor.execute("""
        SELECT sku, price, weight, polish, packing, freight, postage,
               cleaning, testing, profit_margin
        FROM inventory
    """)
    items = cursor.fetchall()
    conn.close()

    updated = 0
    errors = []
    from products.models import Product as EshopProduct
    for item in items:
        try:
            sku, buy, weight_g, polish, packing, freight_override, postage, cleaning, testing, item_profit = item
            buy = float(buy or 0)
            weight_g = float(weight_g or 0)
            polish = float(polish or 0)
            packing = float(packing or 0)
            freight = float(freight_override or 0) or round(weight_g * FREIGHT_RATE / 1000, 2)
            postage = float(postage or 0)
            cleaning = float(cleaning or 0)
            testing = float(testing or 0)
            item_profit = float(item_profit or 0)
            profit_mult = 1 + (item_profit / 100) if item_profit > 0 else DEFAULT_PROFIT
            total_pkr = buy + polish + packing + freight + cleaning + testing
            cost_eur = total_pkr / PKR_EUR
            sell_price = round((cost_eur * profit_mult + postage) / (1 - COMMISSION), 2)
            if sell_price > 0:
                rows = EshopProduct.objects.filter(sku=str(sku)).update(price=sell_price)
                if rows:
                    updated += 1
        except Exception as e:
            errors.append(f'SKU {item[0]}: {str(e)}')

    return JsonResponse({
        'success': True,
        'updated': updated,
        'errors': errors[:10],
        'total': len(items)
    })


# ── SHIPPING RATES ──
from .models import ShippingRate

@staff_member_required
def shipping_rates(request):
    rates = ShippingRate.objects.all()
    return render(request, 'dashboard/postage_rates.html', {'rates': rates})

@staff_member_required
def save_shipping_rate(request):
    if request.method == 'POST':
        rate_id = request.POST.get('rate_id')
        country = request.POST.get('country')
        country_code = request.POST.get('country_code', '')
        standard_price = request.POST.get('standard_price', 0)
        tracked_price = request.POST.get('tracked_price', 15)
        is_active = request.POST.get('is_active') == 'on'
        has_free_postage = request.POST.get('has_free_postage') == 'on'
        if rate_id:
            rate = ShippingRate.objects.get(id=rate_id)
            rate.country = country
            rate.country_code = country_code
            rate.standard_price = standard_price
            rate.tracked_price = tracked_price
            rate.is_active = is_active
            rate.has_free_postage = has_free_postage
            rate.save()
        else:
            if ShippingRate.objects.filter(country__iexact=country).exists():
                rates = ShippingRate.objects.all()
                return render(request, 'dashboard/postage_rates.html', {
                    'rates': rates,
                    'error': f"{country} already exists in shipping rates!"
                })
            ShippingRate.objects.create(
                country=country,
                country_code=country_code,
                standard_price=standard_price,
                tracked_price=tracked_price,
                is_active=is_active,
                has_free_postage=has_free_postage
            )
    return redirect('dashboard:shipping_rates')

@staff_member_required
def delete_shipping_rate(request, rate_id):
    ShippingRate.objects.filter(id=rate_id).delete()
    return redirect('dashboard:shipping_rates')


from django.http import JsonResponse

@staff_member_required
def shipping_rate_api(request):
    country = request.GET.get('country', '').strip()
    try:
        rate = ShippingRate.objects.get(country__iexact=country, is_active=True)
        return JsonResponse({'tracked': float(rate.tracked_price), 'standard': float(rate.standard_price)})
    except ShippingRate.DoesNotExist:
        return JsonResponse({'tracked': 15.00, 'standard': 0.00})


@staff_member_required
def toggle_free_shipping(request, rate_id):
    try:
        rate = ShippingRate.objects.get(id=rate_id)
        rate.has_free_postage = not rate.has_free_postage
        rate.save()
        return JsonResponse({'success': True, 'has_free_postage': rate.has_free_postage})
    except ShippingRate.DoesNotExist:
        return JsonResponse({'success': False})


@staff_member_required
def toggle_active_shipping(request, rate_id):
    try:
        rate = ShippingRate.objects.get(id=rate_id)
        rate.is_active = not rate.is_active
        rate.save()
        return JsonResponse({'success': True, 'is_active': rate.is_active})
    except ShippingRate.DoesNotExist:
        return JsonResponse({'success': False})
