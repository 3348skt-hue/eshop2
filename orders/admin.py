from django.contrib import admin
from django.utils.html import format_html
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "quantity", "price")
    readonly_fields = ("product_name", "quantity", "price")
    can_delete = False

    # ✅ Override to prevent showing the object link/title
    verbose_name = ""
    verbose_name_plural = "Order Items"

    # ✅ Add custom CSS
    class Media:
        css = {
            'all': ('orders/css/custom_admin.css',)
        }

    # ✅ This prevents the change form link from appearing
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "id", "full_name", "email", "total_amount", "paid",
                    "created_at")
    list_filter = ("paid", "created_at")
    search_fields = ("email", "full_name", "order_number")

    exclude = ("shipping_address",)

    readonly_fields = (
        "order_number",
        "full_name",
        "email",
        "phone",
        "formatted_shipping_address",
        "stripe_payment_intent",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]

    def total_amount(self, obj):
        """Calculate and display the total order amount"""
        if hasattr(obj, 'total') and obj.total:
            return f"€{obj.total:.2f}"

        total = sum(item.price * item.quantity for item in obj.items.all())
        return f"€{total:.2f}"

    total_amount.short_description = "Total"

    def formatted_shipping_address(self, obj):
        """Display shipping address in a readable format"""
        if not obj.shipping_address:
            return "No address provided"

        addr = obj.shipping_address
        address_html = f"""
        {addr.get('line1', '')}<br>
        {addr.get('city', '')} {addr.get('postal_code', '')}<br>
        {addr.get('country', '')}
        """
        return format_html(address_html)

    formatted_shipping_address.short_description = "Shipping Address"
