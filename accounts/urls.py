from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.BookstoreLoginView.as_view(), name="login"),
    path("logout/", views.BookstoreLogoutView.as_view(), name="logout"),
    path("me/", views.profile, name="profile"),
]
