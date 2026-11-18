"""URLconf for SEC-19: the real routes plus one view that fails like a database error would."""

from django.urls import path

from bookstore.urls import urlpatterns as real_urlpatterns


def boom(request):
    raise RuntimeError('relation "secret-table-name" does not exist')


urlpatterns = [path("boom/", boom), *real_urlpatterns]
