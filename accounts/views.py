from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render

from .forms import LoginForm


class BookstoreLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class BookstoreLogoutView(LogoutView):
    pass


@login_required
def profile(request):
    return render(request, "accounts/profile.html")
