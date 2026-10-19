from django.contrib import admin
from django.urls import path
from catalog.views import catalog, listing_add, seller_listings
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [path("", catalog, name="catalog"),path("seller/new/", listing_add, name="listing_add"),path("seller/", seller_listings, name="seller_listings"),path("admin/", admin.site.urls)]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
