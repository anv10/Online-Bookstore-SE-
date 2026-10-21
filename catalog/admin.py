from django.contrib import admin
from .models import Book, BookImage

class BookImageInline(admin.TabularInline):
    model = BookImage
    extra = 0

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ["title", "seller", "price", "stock", "condition", "status"]
    list_filter = ["status", "category"]
    search_fields = ["title", "isbn", "seller__email"]
    inlines = [BookImageInline]
