import os
import pymysql
import datetime
from ebaysdk.trading import Connection as Trading

api = Trading(config_file='/home/maksupplies/eshop2/ebay.yaml')

conn = pymysql.connect(
    host='maksupplies.mysql.pythonanywhere-services.com',
    user='maksupplies',
    passwd=os.environ.get('DB_PASS', ''),
    database='maksupplies$default',
    autocommit=True
)
cursor = conn.cursor()

# Check orders from last 2 days to catch any missed
date_from = datetime.datetime.now() - datetime.timedelta(days=2)

try:
    response = api.execute('GetOrders', {
        'IncludeFinalValueFee': 'True',
        'DetailLevel': 'ReturnAll',
        'CreateTimeFrom': date_from,
        'CreateTimeTo': datetime.datetime.now()
    })
    apicall = response.dict()
    orders = apicall.get('OrderArray', {}).get('Order', [])
    if not isinstance(orders, list):
        orders = [orders]

    for order in orders:
        transactions = order['TransactionArray']['Transaction']
        if not isinstance(transactions, list):
            transactions = [transactions]

        for item in transactions:
            try:
                orderid = order['OrderID']
                itemid = item['Item']['ItemID']

                # Check if order already exists
                cursor.execute(
                    "SELECT EXISTS(SELECT * FROM saleorder WHERE orderid=%s AND itemid=%s)",
                    (orderid, itemid)
                )
                if cursor.fetchone()[0]:
                    print(f'EXISTS: {orderid} {itemid}')
                    continue

                sku = item['Item']['SKU']
                quantity = int(item['QuantityPurchased'])

                # Get weight from inventory
                cursor.execute("SELECT weight FROM inventory WHERE sku=%s", (sku,))
                weight_row = cursor.fetchone()
                weight = weight_row[0] if weight_row else 0

                # Insert order
                cursor.execute("""
                    INSERT INTO saleorder
                    (userid,name,street1,street2,city,state,postcode,country,phone,
                     orderid,total,record,postcharge,quantity,time,itemid,site,currency,price,title,sku,weight)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    order['BuyerUserID'],
                    order['ShippingAddress']['Name'],
                    order['ShippingAddress']['Street1'],
                    order['ShippingAddress'].get('Street2', ''),
                    order['ShippingAddress']['CityName'],
                    order['ShippingAddress']['StateOrProvince'],
                    order['ShippingAddress']['PostalCode'],
                    order['ShippingAddress']['CountryName'],
                    order['ShippingAddress']['Phone'],
                    orderid,
                    order['Total']['value'],
                    order['ShippingDetails']['SellingManagerSalesRecordNumber'],
                    order['ShippingServiceSelected']['ShippingServiceCost']['value'],
                    quantity,
                    item['CreatedDate'],
                    itemid,
                    item['Item']['Site'],
                    item['TransactionPrice']['_currencyID'],
                    item['TransactionPrice']['value'],
                    item['Item']['Title'],
                    sku,
                    weight
                ))
                print(f'INSERTED: {orderid} SKU:{sku}')

                # Reduce inventory stock
                cursor.execute("UPDATE inventory SET stock=stock-%s, sale=sale+%s WHERE sku=%s",
                               (quantity, quantity, sku))

                # Get new stock level
                cursor.execute("SELECT stock FROM inventory WHERE sku=%s", (sku,))
                new_stock = cursor.fetchone()[0]

                # Sync to Django products
                cursor.execute("UPDATE products_product SET stock=%s WHERE sku=%s", (new_stock, sku))

                # Update eBay listings
                cursor.execute("SELECT itemid FROM ebaylisting WHERE sku=%s", (sku,))
                listings = cursor.fetchall()
                for listing in listings:
                    try:
                        api.execute('ReviseFixedPriceItem', {
                            'Item': {'ItemID': listing[0], 'Quantity': new_stock}
                        })
                        print(f'eBay stock updated: {listing[0]}')
                    except Exception as e:
                        print(f'eBay update error: {e}')

            except Exception as e:
                print(f'Error processing item: {e}')
                continue

except Exception as e:
    print(f'API Error: {e}')

conn.close()
print('Sync complete:', datetime.datetime.now())
