import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from security import events, ratelimit

from .forms import (
    AccountDeletionForm,
    LoginForm,
    PasswordResetOTPForm,
    PasswordResetRequestForm,
    PersonalDataForm,
    RegistrationForm,
    SetNewPasswordForm,
)
from .models import MAX_OTP_ATTEMPTS, MAX_OTP_LIFETIME, PasswordResetOTP, User

# The emailed link's token is moved into the session and replaced by this
# placeholder, so it does not stay in the address bar, history or Referer (SEC-18).
INTERNAL_RESET_TOKEN = "set-password"
RESET_TOKEN_SESSION_KEY = "_password_reset_token"

logger = logging.getLogger(__name__)


@sensitive_post_parameters("password", "confirm_password")
@ratelimit.limit_by_ip("register")
def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid() and form.save():
            messages.success(request, "Account created. You can now log in.")
            return redirect("register")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@method_decorator(ratelimit.limit_by_ip("login"), name="dispatch")
class BookstoreLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class BookstoreLogoutView(LogoutView):
    pass


@login_required
def profile(request):
    return render(
        request,
        "accounts/profile.html",
        {"data_form": PersonalDataForm(instance=request.user), "delete_form": AccountDeletionForm(request.user)},
    )


@ratelimit.limit_by_ip("password_reset")
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        # SEC-6: at most a few reset messages per account per hour, so the feature cannot
        # be used to flood someone's inbox. The reply stays the same (SEC-4).
        if user and not ratelimit.hit("password_reset_account", user.pk):
            events.record(events.Kind.RATE_LIMITED, request, user=user, detail="password_reset_account")
            user = None
        # Only accounts with an email can receive the link; the reply is the same either way.
        if user and user.email:
            events.record(events.Kind.RESET_REQUESTED, request, user=user)
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


@sensitive_post_parameters("code")
@ratelimit.limit_by_ip("password_reset_otp")
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
            events.record(events.Kind.RESET_OTP_FAILED, request, user=user, detail=f"attempt {otp.attempts}")
            form.add_error("code", "Incorrect OTP")
    return render(request, "accounts/password_reset_otp.html", {"form": form})


@sensitive_post_parameters("password", "confirm_password")
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
        events.record(events.Kind.RESET_COMPLETED, request, user=user, detail="otp")
        messages.success(request, "Your password has been changed. You can now log in.")
        return redirect("login")
    return render(request, "accounts/password_reset_otp_set.html", {"form": form})


@sensitive_post_parameters("password", "confirm_password")
def password_reset_confirm(request, uidb64, token):
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if token == INTERNAL_RESET_TOKEN:
        token = request.session.get(RESET_TOKEN_SESSION_KEY, "")
    elif request.method == "GET" and user is not None and default_token_generator.check_token(user, token):
        request.session[RESET_TOKEN_SESSION_KEY] = token
        return redirect("password_reset_confirm", uidb64=uidb64, token=INTERNAL_RESET_TOKEN)
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "accounts/password_reset_invalid.html", status=400)
    form = SetNewPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.session.pop(RESET_TOKEN_SESSION_KEY, None)
        events.record(events.Kind.RESET_COMPLETED, request, user=user, detail="link")
        messages.success(request, "Password changed. You can now log in.")
        return redirect("login")
    return render(request, "accounts/password_reset_confirm.html", {"form": form})


@login_required
@require_POST
def profile_update(request):
    """Correct your own personal data (SEC-35)."""
    form = PersonalDataForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        events.record(events.Kind.ACCOUNT_UPDATED, request)
        messages.success(request, "Your details were updated.")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"data_form": form, "delete_form": AccountDeletionForm(request.user)})


@login_required
@sensitive_post_parameters("password")
@require_POST
def profile_delete(request):
    """Delete your personal data on request (SEC-35).

    Contact details are erased and sign-in is disabled. Orders and invoices are
    kept for legal and accounting reasons and stay linked to the anonymised row.
    """
    user = request.user
    form = AccountDeletionForm(user, request.POST)
    if not form.is_valid():
        return render(request, "accounts/profile.html", {"data_form": PersonalDataForm(instance=user), "delete_form": form})
    user.email = None
    user.phone = None
    user.full_name = ""
    user.is_active = False
    user.removed_at = timezone.now()
    user.set_unusable_password()
    user.save()
    user.reset_otps.all().delete()
    user.wishlist_items.all().delete()
    events.record(events.Kind.ACCOUNT_DELETED, request, user=user)
    logout(request)
    messages.success(request, "Your account and personal details were deleted. Order records are kept as the law requires.")
    return redirect("catalog")


def privacy(request):
    """Privacy notice linked from registration and every page (SEC-34, NFR-10)."""
    return render(request, "accounts/privacy.html")
