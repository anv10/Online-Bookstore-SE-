from django.contrib import admin

from .models import AccountAction


@admin.register(AccountAction)
class AccountActionAdmin(admin.ModelAdmin):
    list_display = ("target", "action", "admin", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("target__email", "target__phone", "admin__email", "reason")
    readonly_fields = ("target", "admin", "action", "reason", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
