from django.urls import path

from . import moderation, views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.BookstoreLoginView.as_view(), name="login"),
    path("logout/", views.BookstoreLogoutView.as_view(), name="logout"),
    path("me/", views.profile, name="profile"),
    path("admin/users/", moderation.user_list, name="user_admin_list"),
    path("admin/users/<int:pk>/", moderation.user_detail, name="user_admin_detail"),
]
