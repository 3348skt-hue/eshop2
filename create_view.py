view_code = '''

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
        new_cost = float(data.get('cost', 0))
        if source == 'ebay':
            cursor.execute("UPDATE saleorder SET cost=%s WHERE id=%s", (new_cost, row_id))
        conn.close()
        return JsonResponse({'ok': True})

    ebay_where = ["1=1"]
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

    if source_filter in ('all', 'ebay'):
        ebay_sql = f"""
            SELECT s.id, s.orderid, s.name, s.country, s.time, s.sku, i.title,
                s.quantity,
                (s.price * s.quantity + IFNULL(s.postcharge,0)) * IFNULL(s.rate,1) as revenue,
                IFNULL(s.cost,0) * s.quantity as cost,
                IFNULL(s.postage,0) as postage,
                IFNULL(s.fee,0) * IFNULL(s.rate,1) as fee,
                s.currency, s.site
            FROM saleorder s
            LEFT JOIN inventory i ON i.sku = s.sku
            WHERE {' AND '.join(ebay_where)}
        """
        cursor.execute(ebay_sql, params_ebay)
        for r in cursor.fetchall():
            revenue = float(r[8] or 0)
            cost = float(r[9] or 0)
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
                IFNULL(i.cost, 0) * oi.quantity as cost,
                0, 0, 'GBP', 'eshop'
            FROM orders_order o
            JOIN orders_orderitem oi ON oi.order_id = o.id
            LEFT JOIN inventory i ON i.sku = oi.sku
            WHERE {' AND '.join(eshop_where)}
        """
        cursor.execute(eshop_sql, params_eshop)
        for r in cursor.fetchall():
            revenue = float(r[8] or 0)
            cost = float(r[9] or 0)
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
'''

with open('/home/maksupplies/eshop2/dashboard/views.py', 'a') as f:
    f.write(view_code)

print("✅ View added successfully!")
