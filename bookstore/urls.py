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

from bookstore.views import support
from cart.views import cart_add, cart_detail, cart_remove, cart_update
from catalog import moderation
from catalog.views import book_detail, catalog, listing_add, listing_edit, listing_remove, seller_listings
from orders.seller_views import seller_order_deliver, seller_order_detail, seller_order_ship, seller_orders
from orders.views import apply_coupon, checkout, checkout_cancel, checkout_complete, invoice_download, invoice_view, order_confirmation, order_detail, order_list, remove_coupon
from reviews.views import submit_review
from wishlist.views import wishlist_add, wishlist_detail, wishlist_remove, wishlist_to_cart

urlpatterns = [
    path("", catalog, name="catalog"),
    path("support/", support, name="support"),
    path("books/<int:pk>/", book_detail, name="book_detail"),
    path("books/<int:pk>/review/", submit_review, name="review_submit"),
    path("seller/new/", listing_add, name="listing_add"),
    path("seller/", seller_listings, name="seller_listings"),
    path("seller/<int:pk>/edit/", listing_edit, name="listing_edit"),
    path("seller/<int:pk>/remove/", listing_remove, name="listing_remove"),
    path("moderation/verify/", moderation.verify, name="moderation_verify"),
    path("moderation/", moderation.queue, name="moderation_queue"),
    path("moderation/<int:pk>/", moderation.decide, name="moderation_decide"),
    path("seller/orders/", seller_orders, name="seller_orders"),
    path("seller/orders/<int:order_id>/", seller_order_detail, name="seller_order_detail"),
    path("seller/orders/<int:order_id>/ship/", seller_order_ship, name="seller_order_ship"),
    path("seller/orders/<int:order_id>/deliver/", seller_order_deliver, name="seller_order_deliver"),
    path("orders/", order_list, name="order_list"),
    path("orders/<int:order_id>/", order_detail, name="order_detail"),
    path("orders/<int:order_id>/invoice/", invoice_view, name="invoice_view"),
    path("orders/<int:order_id>/invoice/download/", invoice_download, name="invoice_download"),
    path("cart/", cart_detail, name="cart"),
    path("cart/add/<int:book_id>/", cart_add, name="cart_add"),
    path("cart/items/<int:item_id>/update/", cart_update, name="cart_update"),
    path("cart/items/<int:item_id>/remove/", cart_remove, name="cart_remove"),
    path("wishlist/", wishlist_detail, name="wishlist"),
    path("wishlist/add/<int:book_id>/", wishlist_add, name="wishlist_add"),
    path("wishlist/items/<int:item_id>/remove/", wishlist_remove, name="wishlist_remove"),
    path("wishlist/items/<int:item_id>/to-cart/", wishlist_to_cart, name="wishlist_to_cart"),
    path("checkout/", checkout, name="checkout"),
    path("checkout/coupon/", apply_coupon, name="apply_coupon"),
    path("checkout/coupon/remove/", remove_coupon, name="remove_coupon"),
    path("checkout/complete/", checkout_complete, name="checkout_complete"),
    path("checkout/cancel/", checkout_cancel, name="checkout_cancel"),
    path("orders/<int:pk>/confirmation/", order_confirmation, name="order_confirmation"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
