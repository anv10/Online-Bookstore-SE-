from django.contrib import admin

from .models import SecurityEvent


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    """Read-only for authorised staff: the log cannot be added to, edited or deleted here (SEC-32)."""

    list_display = ("created_at", "kind", "user_id_ref", "ip_address", "path", "detail")
    list_filter = ("kind", "created_at")
    search_fields = ("detail", "path", "ip_address")
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
