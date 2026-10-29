"""
URL configuration for bookstore project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from cart.views import cart_add, cart_detail, cart_remove, cart_update
from catalog import moderation
from catalog.views import book_detail, catalog, listing_add, listing_edit, listing_remove, seller_listings
from orders.views import invoice_download, invoice_view, order_detail, order_list

urlpatterns = [
    path("", catalog, name="catalog"),
    path("books/<int:pk>/", book_detail, name="book_detail"),
    path("seller/new/", listing_add, name="listing_add"),
    path("seller/", seller_listings, name="seller_listings"),
    path("seller/<int:pk>/edit/", listing_edit, name="listing_edit"),
    path("seller/<int:pk>/remove/", listing_remove, name="listing_remove"),
    path("moderation/verify/", moderation.verify, name="moderation_verify"),
    path("moderation/", moderation.queue, name="moderation_queue"),
    path("moderation/<int:pk>/", moderation.decide, name="moderation_decide"),
    path("orders/", order_list, name="order_list"),
    path("orders/<int:order_id>/", order_detail, name="order_detail"),
    path("orders/<int:order_id>/invoice/", invoice_view, name="invoice_view"),
    path("orders/<int:order_id>/invoice/download/", invoice_download, name="invoice_download"),
    path("cart/", cart_detail, name="cart"),
    path("cart/add/<int:book_id>/", cart_add, name="cart_add"),
    path("cart/items/<int:item_id>/update/", cart_update, name="cart_update"),
    path("cart/items/<int:item_id>/remove/", cart_remove, name="cart_remove"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
