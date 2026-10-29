"""Listing moderation with an email second factor and atomic audit records."""
from datetime import timedelta
import hashlib
import secrets

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator

from .models import AdminChallenge, Book, ModerationEvent


def is_moderator(user):
    return user.is_authenticated and user.is_active and user.is_staff and user.has_perm("catalog.change_book")


def _check_admin(request):
    if not is_moderator(request.user):
        raise PermissionDenied


def _verified(request):
    value = request.session.get("moderation_verified_until", 0)
    return value > timezone.now().timestamp()


class VerificationForm(forms.Form):
    code = forms.RegexField(r"^[0-9]{6}$", max_length=6, label="Six digit email code", widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))


class DecisionForm(forms.Form):
    status = forms.ChoiceField(choices=[(v, label) for v, label in Book.Status.choices if v != Book.Status.PENDING])
    expected_status = forms.ChoiceField(choices=Book.Status.choices, widget=forms.HiddenInput)
    reason = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


@login_required
@require_http_methods(["GET", "POST"])
def verify(request):
    _check_admin(request)
    if _verified(request):
        return redirect("moderation_queue")
    form = VerificationForm(request.POST if request.method == "POST" and request.POST.get("action") == "verify" else None)
    if request.method == "POST":
        if request.POST.get("action") == "send":
            if not request.user.email:
                messages.error(request, "An administrator must configure your email address before you can moderate.")
            else:
                now = timezone.now()
                # The account row serializes first-time challenge creation across sessions.
                with transaction.atomic():
                    get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    challenge, _ = AdminChallenge.objects.get_or_create(user=request.user, defaults={"window_started": now})
                    if now >= challenge.window_started + timedelta(hours=1):
                        challenge.window_started, challenge.requests = now, 0
                    if challenge.requests >= 5:
                        messages.error(request, "Too many code requests. Try again after one hour.")
                    else:
                        code = f"{secrets.randbelow(1000000):06d}"
                        nonce = secrets.token_urlsafe(32)
                        challenge.requests += 1
                        challenge.code_hash = make_password(code)
                        challenge.session_hash = hashlib.sha256(nonce.encode()).hexdigest()
                        challenge.expires_at = now + timedelta(minutes=10)
                        challenge.attempts = 0
                        challenge.save()
                        request.session["moderation_nonce"] = nonce
                        try:
                            delivered = send_mail("Bookstore admin verification", f"Your verification code is {code}. It expires in 10 minutes.", None, [request.user.email])
                            if delivered != 1:
                                raise RuntimeError("Email not accepted")
                        except Exception:
                            # Never expose delivery exceptions or verification codes in logs.
                            challenge.code_hash = ""
                            challenge.save(update_fields=["code_hash"])
                            messages.error(request, "The verification email could not be sent. Check email configuration and retry.")
                        else:
                            messages.success(request, "Verification code sent to your account email.")
        elif request.POST.get("action") == "verify" and form.is_valid():
            with transaction.atomic():
                challenge = AdminChallenge.objects.select_for_update().filter(user=request.user).first()
                nonce = request.session.get("moderation_nonce", "")
                valid = bool(challenge and challenge.code_hash and nonce and challenge.expires_at > timezone.now() and challenge.attempts < 5 and secrets.compare_digest(challenge.session_hash, hashlib.sha256(nonce.encode()).hexdigest()))
                if valid:
                    challenge.attempts += 1
                    valid = check_password(form.cleaned_data["code"], challenge.code_hash)
                    if valid:
                        challenge.code_hash = ""
                    challenge.save(update_fields=["attempts", "code_hash"])
                if valid:
                    request.session.pop("moderation_nonce", None)
                    request.session["moderation_verified_until"] = (timezone.now() + timedelta(minutes=30)).timestamp()
                    return redirect("moderation_queue")
                form.add_error("code", "Invalid or expired code. Request a new code if needed.")
    return render(request, "catalog/moderation_verify.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def queue(request):
    _check_admin(request)
    if not _verified(request):
        return redirect("moderation_verify")
    status = request.GET.get("status", Book.Status.PENDING)
    if status not in Book.Status.values:
        status = Book.Status.PENDING
    books = Book.objects.filter(status=status).select_related("seller").order_by("created_at", "pk")
    return render(request, "catalog/moderation_queue.html", {"page_obj": Paginator(books, 20).get_page(request.GET.get("page")), "selected_status": status, "statuses": Book.Status.choices})


@login_required
@require_http_methods(["GET", "POST"])
def decide(request, pk):
    _check_admin(request)
    if not _verified(request):
        return redirect("moderation_verify")
    book = get_object_or_404(Book.objects.select_related("seller"), pk=pk)
    form = DecisionForm(request.POST if request.method == "POST" else None, initial={"expected_status": book.status})
    status_code = 200
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            book = get_object_or_404(Book.objects.select_for_update(), pk=pk)
            target = form.cleaned_data["status"]
            if book.status != form.cleaned_data["expected_status"]:
                form.add_error(None, "This listing changed since you opened it. Reload before deciding.")
                status_code = 409
            elif book.status == target:
                form.add_error(None, f"Listing is already {book.get_status_display().lower()}.")
            elif book.status == Book.Status.REMOVED:
                form.add_error(None, "Removed listings cannot be reinstated.")
            elif target == Book.Status.APPROVED and (not book.seller_id or not book.seller.is_active):
                form.add_error(None, "An active seller is required before approval.")
            else:
                previous = book.status
                book.status = target
                book.save(update_fields=["status"])
                ModerationEvent.objects.create(book=book, admin=request.user, previous_status=previous, new_status=target, reason=form.cleaned_data["reason"])
                messages.success(request, "Moderation decision saved.")
                return redirect("moderation_queue")
    return render(request, "catalog/moderation_decide.html", {"book": book, "form": form, "events": book.moderation_events.select_related("admin")[:20]}, status=status_code)
