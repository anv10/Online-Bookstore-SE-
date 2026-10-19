from django.contrib import admin
from django.urls import path
from catalog.views import catalog

urlpatterns = [path("", catalog, name="catalog"),path("admin/", admin.site.urls)]
