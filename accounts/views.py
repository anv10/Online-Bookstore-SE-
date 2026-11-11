import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .forms import LoginForm, PasswordResetOTPForm, PasswordResetRequestForm, RegistrationForm, SetNewPasswordForm
from .models import MAX_OTP_ATTEMPTS, MAX_OTP_LIFETIME, PasswordResetOTP, User

logger = logging.getLogger(__name__)


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
            code = f"{secrets.randbelow(1000000):06d}"
            PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).delete()
            PasswordResetOTP.objects.create(
                user=user,
                code_hash=make_password(code),
                expires_at=timezone.now() + MAX_OTP_LIFETIME,
            )
            try:
                send_mail(
                    "Reset your password",
                    f"Use this link to choose a new password. It works once and expires soon:\n{link}\n\n"
                    f"Or enter this code on the reset page: {code}\n",
                    None,
                    [user.email],
                )
            except Exception:
                # Same reply as for an unknown account, so a mail outage does not reveal who has one.
                logger.exception("Could not send password reset email for user %s", user.pk)
        return redirect("password_reset_done")
    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_done(request):
    return render(request, "accounts/password_reset_done.html")


def password_reset_otp(request):
    """Enter the emailed six digit code (Test Plan FR-14_UT02)."""
    form = PasswordResetOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        otp = user.reset_otps.first() if user else None
        if otp is None:
            form.add_error("code", "Incorrect OTP")
        elif otp.used_at is not None:
            form.add_error("code", "This reset link/OTP is no longer valid")
        elif otp.expires_at <= timezone.now():
            form.add_error("code", "OTP has expired, please request a new one")
        elif otp.attempts >= MAX_OTP_ATTEMPTS:
            # Burned out by guessing: keep the generic reply so the code cannot be probed.
            form.add_error("code", "Incorrect OTP")
        elif check_password(form.cleaned_data["code"], otp.code_hash):
            otp.used_at = timezone.now()
            otp.save(update_fields=["used_at"])
            request.session["otp_reset_user"] = user.pk
            return redirect("password_reset_otp_set")
        else:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            form.add_error("code", "Incorrect OTP")
    return render(request, "accounts/password_reset_otp.html", {"form": form})


def password_reset_otp_set(request):
    user = User.objects.filter(pk=request.session.get("otp_reset_user"), is_active=True).first()
    if user is None:
        messages.error(request, "Start the reset again to choose a new password.")
        return redirect("password_reset")
    form = SetNewPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["password"])
        user.save(update_fields=["password"])
        request.session.pop("otp_reset_user", None)
        messages.success(request, "Your password has been changed. You can now log in.")
        return redirect("login")
    return render(request, "accounts/password_reset_otp_set.html", {"form": form})


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
