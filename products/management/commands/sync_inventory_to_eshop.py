from django.core.management.base import BaseCommand
from django.db import connection
from products.models import Product, Category, SubCategory, Store


class Command(BaseCommand):
    help = 'Sync MySQL inventory table directly into Django products_product — no CSV needed'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview only, no changes')
        parser.add_argument('--sku', type=str, help='Sync a single SKU only')
        parser.add_argument('--skip-no-photo', action='store_true', help='Skip new products with no photo')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        single_sku = options.get('sku')
        skip_no_photo = options.get('skip_no_photo', True)  # default: skip no-photo new products

        store, _ = Store.objects.get_or_create(name="Main Store")

        with connection.cursor() as cursor:
            if single_sku:
                cursor.execute(
                    "SELECT sku, title, price, stock, storecat, photo FROM inventory WHERE sku=%s",
                    (single_sku,)
                )
            else:
                cursor.execute(
                    "SELECT sku, title, price, stock, storecat, photo FROM inventory WHERE title IS NOT NULL AND title != ''"
                )
            rows = cursor.fetchall()

        created = updated = skipped = errors = 0

        for row in rows:
            sku, title, price, stock, storecat, photo = row

            if not sku or not title:
                skipped += 1
                continue

            try:
                # Check if product already exists
                try:
                    existing = Product.objects.get(sku=str(sku))
                    is_new = False
                    existing_image = existing.image or ''
                    existing_price = existing.price if existing.price and existing.price > 0 else float(price or 0)
                except Product.DoesNotExist:
                    is_new = True
                    existing_image = ''
                    existing_price = float(price or 0)

                # Skip NEW products with no photo
                if is_new and skip_no_photo and not photo:
                    skipped += 1
                    continue

                # Use inventory photo for new products, preserve existing for old ones
                if is_new:
                    final_image = photo or ''
                else:
                    # For existing: use inventory photo if no image yet, else keep existing
                    final_image = existing_image if existing_image else (photo or '')

                # Parse category from storecat
                cat_name = 'General'
                subcat_name = None
                if storecat:
                    parts = [p.strip() for p in storecat.split('/') if p.strip()]
                    if len(parts) >= 2:
                        cat_name = parts[1]
                    if len(parts) >= 3:
                        subcat_name = parts[2]

                category, _ = Category.objects.get_or_create(name=cat_name)

                subcategory = None
                if subcat_name:
                    subcategory, _ = SubCategory.objects.get_or_create(
                        name=subcat_name,
                        category=category
                    )

                if dry_run:
                    self.stdout.write(
                        f'{"NEW" if is_new else "UPD"}: SKU={sku} | {title[:40]} | '
                        f'price={existing_price} | stock={stock} | '
                        f'image={"YES" if final_image else "NO"}'
                    )
                    continue

                obj, was_created = Product.objects.update_or_create(
                    sku=str(sku),
                    defaults={
                        'name': title[:200],
                        'description': title,
                        'price': existing_price,
                        'stock': int(stock or 0),
                        'category': category,
                        'subcategory': subcategory,
                        'store': store,
                        'image': final_image,
                    }
                )

                if was_created:
                    created += 1
                    self.stdout.write(f'CREATED: SKU={sku} | {title[:40]} | image={"YES" if final_image else "NO"}')
                else:
                    updated += 1

            except Exception as e:
                errors += 1
                self.stdout.write(f'ERROR: SKU={sku} — {e}')

        self.stdout.write(
            f'\n{"PREVIEW" if dry_run else "DONE"} — '
            f'Created: {created} | Updated: {updated} | '
            f'Skipped: {skipped} | Errors: {errors} | Total: {len(rows)}'
        )
