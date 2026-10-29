"""Audited account suspension and removal for administrators (FR-12)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import AccountAction, User


class AccountActionForm(forms.Form):
    action = forms.ChoiceField(choices=AccountAction.Action.choices)
    reason = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Why is this action being taken?"}),
    )


def _check_admin(request):
    if not (
        request.user.is_authenticated
        and request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("accounts.change_user")
    ):
        raise PermissionDenied


@login_required
@require_http_methods(["GET"])
def user_list(request):
    _check_admin(request)
    users = User.objects.all().order_by("-date_joined", "-pk")
    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(email__icontains=query) | Q(phone__icontains=query) | Q(full_name__icontains=query)
        )
    status = request.GET.get("status", "active")
    if status == "suspended":
        users = users.filter(suspended_at__isnull=False, removed_at__isnull=True)
    elif status == "removed":
        users = users.filter(removed_at__isnull=False)
    elif status == "active":
        users = users.filter(suspended_at__isnull=True, removed_at__isnull=True, is_active=True)
    elif status != "all":
        status = "active"
        users = users.filter(suspended_at__isnull=True, removed_at__isnull=True, is_active=True)
    return render(
        request,
        "accounts/user_admin_list.html",
        {
            "page_obj": Paginator(users, 20).get_page(request.GET.get("page")),
            "query": query,
            "selected_status": status,
            "statuses": [("active", "Active"), ("suspended", "Suspended"), ("removed", "Removed"), ("all", "All")],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def user_detail(request, pk):
    _check_admin(request)
    target = get_object_or_404(User, pk=pk)
    form = AccountActionForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            target = get_object_or_404(User.objects.select_for_update(), pk=pk)
            action = form.cleaned_data["action"]
            if target.pk == request.user.pk:
                form.add_error(None, "You cannot suspend or remove your own account.")
            elif target.is_superuser and not request.user.is_superuser:
                form.add_error(None, "Only a superuser can moderate another superuser.")
            elif target.is_removed:
                form.add_error(None, "Account is already removed.")
            elif target.is_suspended and action == AccountAction.Action.SUSPEND:
                form.add_error(None, "Account is already suspended.")
            else:
                now = timezone.now()
                if action == AccountAction.Action.SUSPEND:
                    target.suspended_at = now
                    target.is_active = False
                    target.save(update_fields=["suspended_at", "is_active"])
                    verb = "suspended"
                else:
                    target.removed_at = now
                    target.is_active = False
                    target.save(update_fields=["removed_at", "is_active"])
                    verb = "removed"
                AccountAction.objects.create(
                    target=target,
                    admin=request.user,
                    action=action,
                    reason=form.cleaned_data["reason"],
                )
                messages.success(request, f"Account {target} was {verb}.")
                return redirect("user_admin_detail", pk=target.pk)

    return render(
        request,
        "accounts/user_admin_detail.html",
        {
            "target": target,
            "form": form,
            "actions": target.moderation_actions_received.select_related("admin")[:50],
        },
    )
