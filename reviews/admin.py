from django.contrib import admin, messages

from security import events

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("book", "user", "rating", "status", "held_reason", "created_at", "updated_at")
    list_filter = ("status", "rating", "created_at")
    search_fields = ("book__title", "user__email", "comment")
    readonly_fields = ("created_at", "updated_at", "held_reason")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve and publish selected reviews")
    def approve_reviews(self, request, queryset):
        self._decide(request, queryset, Review.Status.PUBLISHED)

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        self._decide(request, queryset, Review.Status.REJECTED)

    def _decide(self, request, queryset, status):
        ids = list(queryset.values_list("pk", flat=True))
        queryset.update(status=status)
        for pk in ids:
            events.record(events.Kind.ADMIN_ACTION, request, detail=f"review {pk} -> {status}")
        self.message_user(request, f"{len(ids)} review(s) marked {status}.", messages.SUCCESS)
