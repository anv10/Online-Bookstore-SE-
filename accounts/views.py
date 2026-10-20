from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import LoginForm, RegistrationForm


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid() and form.save():
            messages.success(request, "Account created. You can now log in.")
            return redirect("register")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


class BookstoreLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class BookstoreLogoutView(LogoutView):
    pass


@login_required
def profile(request):
    return render(request, "accounts/profile.html")
