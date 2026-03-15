from django.db import models
from django.utils import timezone


class Order(models.Model):
    order_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, default='')
    shipping_address = models.JSONField()
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('posted', 'Posted'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    paid = models.BooleanField(default=False)
    stripe_payment_intent = models.CharField(max_length=200, blank=True, default='')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        # ✅ Return empty string to prevent duplicate display in admin
        return ""

    def get_total(self):
        return self.quantity * self.price
