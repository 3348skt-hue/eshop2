import os
import pymysql
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

# First check what site each existing listing is on using GetItem
cursor.execute("SELECT itemid FROM ebaylisting WHERE site = '' OR site IS NULL")
items_to_update = cursor.fetchall()

print(f"Checking site for {len(items_to_update)} listings...")

for (itemid,) in items_to_update:
    try:
        response = api.execute('GetItem', {
            'ItemID': itemid,
            'DetailLevel': 'ReturnAll'
        })
        data = response.dict()
        item = data.get('Item', {})
        site = item.get('Site', '').lower()
        currency = item.get('StartPrice', {}).get('_currencyID', '')
        
        # Map eBay site names to our format
        site_map = {
            'ireland': 'ireland',
            'uk': 'uk', 
            'unitedkingdom': 'uk',
            'us': 'usa',
            'unitedstates': 'usa',
            'canada': 'canada',
            'australia': 'australia',
            'germany': 'germany',
            'france': 'france',
        }
        mapped_site = site_map.get(site, site)
        
        cursor.execute("UPDATE ebaylisting SET site=%s, currency=%s WHERE itemid=%s", 
                      (mapped_site, currency, itemid))
        print(f"Updated {itemid}: site={mapped_site} currency={currency}")
    except Exception as e:
        print(f"Error on {itemid}: {e}")

print("\nNow syncing all active listings...")

page = 1
total_inserted = 0
total_skipped = 0
total_updated = 0

while True:
    try:
        response = api.execute('GetMyeBaySelling', {
            'ActiveList': {
                'Include': 'true',
                'Pagination': {
                    'EntriesPerPage': 200,
                    'PageNumber': page
                }
            },
            'DetailLevel': 'ReturnAll'
        })
        data = response.dict()
        active = data.get('ActiveList', {})
        items = active.get('ItemArray', {}).get('Item', [])
        if not items:
            print(f'No items on page {page}, done.')
            break
        if not isinstance(items, list):
            items = [items]

        for item in items:
            try:
                itemid   = item.get('ItemID', '')
                title    = item.get('Title', '')[:100]
                sku      = item.get('SKU', '') or ''
                price    = float(item.get('SellingStatus', {}).get('CurrentPrice', {}).get('value', 0))
                currency = item.get('SellingStatus', {}).get('CurrentPrice', {}).get('_currencyID', '')
                site     = item.get('Site', '').lower()
                status   = item.get('SellingStatus', {}).get('ListingStatus', 'Active')
                catid    = int(item.get('PrimaryCategory', {}).get('CategoryID', 0) or 0)
                category = item.get('PrimaryCategory', {}).get('CategoryName', '')[:25]

                # Map site names
                site_map = {
                    'ireland': 'ireland', 'uk': 'uk', 'unitedkingdom': 'uk',
                    'us': 'usa', 'unitedstates': 'usa', 'canada': 'canada',
                    'australia': 'australia', 'germany': 'germany', 'france': 'france',
                }
                mapped_site = site_map.get(site, site)

                # If currency known, derive site
                if not mapped_site and currency:
                    currency_site = {'EUR': 'ireland', 'GBP': 'uk', 'USD': 'usa', 'CAD': 'canada', 'AUD': 'australia'}
                    mapped_site = currency_site.get(currency, '')

                cursor.execute("SELECT id FROM ebaylisting WHERE itemid=%s", (itemid,))
                if cursor.fetchone():
                    cursor.execute("UPDATE ebaylisting SET site=%s, currency=%s, price=%s, status=%s WHERE itemid=%s",
                                  (mapped_site, currency, price, status, itemid))
                    total_updated += 1
                    continue

                cursor.execute("""
                    INSERT INTO ebaylisting (itemid, sku, title, price, currency, site, status, catid, category, chanel, type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (itemid, sku, title, price, currency, mapped_site, status, catid, category, 'ebay', 1))
                print(f'INSERTED: {itemid} SKU:{sku} site:{mapped_site} currency:{currency}')
                total_inserted += 1

            except Exception as e:
                print(f'Error on item {item.get("ItemID","?")}: {e}')
                continue

        total_pages = int(active.get('PaginationResult', {}).get('TotalNumberOfPages', 1))
        print(f'Page {page}/{total_pages} done.')
        if page >= total_pages:
            break
        page += 1

    except Exception as e:
        print(f'API Error on page {page}: {e}')
        break

conn.close()
print(f'\nDone! Inserted:{total_inserted} | Updated:{total_updated} | Skipped:{total_skipped}')
