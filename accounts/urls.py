from django.urls import path

from . import moderation, views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.BookstoreLoginView.as_view(), name="login"),
    path("logout/", views.BookstoreLogoutView.as_view(), name="logout"),
    path("password-reset/", views.password_reset_request, name="password_reset"),
    path("password-reset/sent/", views.password_reset_done, name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("me/", views.profile, name="profile"),
    path("admin/users/", moderation.user_list, name="user_admin_list"),
    path("admin/users/<int:pk>/", moderation.user_detail, name="user_admin_detail"),
]
