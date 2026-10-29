from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .forms import LoginForm, PasswordResetRequestForm, RegistrationForm, SetNewPasswordForm
from .models import User


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


def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        # Only accounts with an email can receive the link; the reply is the same either way.
        if user and user.email:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = request.build_absolute_uri(reverse("password_reset_confirm", args=[uid, token]))
            send_mail(
                "Reset your password",
                f"Use this link to choose a new password. It works once and expires soon:\n{link}",
                None,
                [user.email],
            )
        return redirect("password_reset_done")
    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_done(request):
    return render(request, "accounts/password_reset_done.html")


def password_reset_confirm(request, uidb64, token):
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "accounts/password_reset_invalid.html", status=400)
    form = SetNewPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Password changed. You can now log in.")
        return redirect("login")
    return render(request, "accounts/password_reset_confirm.html", {"form": form})
