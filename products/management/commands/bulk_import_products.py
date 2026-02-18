import csv
import os
import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from products.models import Product, Category, SubCategory, Store


class Command(BaseCommand):
    help = "Bulk import products from CSV file (supports image URLs)"

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **kwargs):
        file_path = kwargs['csv_file']

        with open(file_path, encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)

            for row in reader:
                row = {k.strip().lower(): v.strip() for k, v in row.items()}

                # ---- STORE ----
                store = None
                if row.get('store'):
                    store, _ = Store.objects.get_or_create(name=row['store'])

                # ---- CATEGORY ----
                if not row.get('category'):
                    continue
                category, _ = Category.objects.get_or_create(name=row['category'])

                # ---- SUBCATEGORY ----
                subcategory = None
                if row.get('subcategory'):
                    subcategory, _ = SubCategory.objects.get_or_create(
                        name=row['subcategory'],
                        category=category
                    )

                # ---- PRODUCT ----
                product = Product(
                    store=store,
                    category=category,
                    subcategory=subcategory,
                    name=row.get('name'),
                    sku=row.get('sku') or None,
                    description=row.get('description', ''),
                    price=row.get('price') or None,
                    stock=int(row['stock']) if row.get('stock', '').isdigit() else 0
                )

                # ---- IMAGE FROM URL ----
                image_url = row.get('image')
                if image_url and image_url.startswith('http'):
                    try:
                        response = requests.get(image_url, timeout=10)
                        response.raise_for_status()

                        file_name = os.path.basename(image_url.split("?")[0])
                        product.image.save(
                            file_name,
                            ContentFile(response.content),
                            save=False
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"Image failed for {product.name}: {e}")
                        )

                product.save()

                self.stdout.write(self.style.SUCCESS(f"Imported: {product.name}"))

        self.stdout.write(self.style.SUCCESS("✅ IMPORT COMPLETED"))
