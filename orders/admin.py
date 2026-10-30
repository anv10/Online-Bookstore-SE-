from django.contrib import admin

from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "active", "expires_at", "times_used", "max_uses")
    list_filter = ("kind", "active")
    search_fields = ("code",)
