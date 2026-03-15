from django.db import models

# Create your models here.


class ShippingRate(models.Model):
    country = models.CharField(max_length=100, unique=True)
    country_code = models.CharField(max_length=5, blank=True, default='')
    standard_price = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    tracked_price = models.DecimalField(max_digits=6, decimal_places=2, default=15.00)
    is_active = models.BooleanField(default=True)
    has_free_postage = models.BooleanField(default=False, help_text="Show free standard postage option for this country")

    class Meta:
        ordering = ['country']

    def __str__(self):
        return f"{self.country} - Standard: €{self.standard_price} / Tracked: €{self.tracked_price}"
