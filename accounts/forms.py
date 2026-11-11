import re

from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from django.db import IntegrityError, transaction

from . import throttle
from .models import User

PHONE_RE = re.compile(r"^\+?\d{7,15}$")


class RegistrationForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        max_length=254,
        error_messages={
            "required": "Email address is required",
            "invalid": "Enter a valid email address",
        },
    )
    phone = forms.CharField(
        label="Phone number",
        max_length=32,
        error_messages={"required": "Phone number is required"},
    )
    password = forms.CharField(widget=forms.PasswordInput, strip=False)
    confirm_password = forms.CharField(widget=forms.PasswordInput, strip=False)

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise ValidationError("An account with this email already exists.")
        return value

    def clean_phone(self):
        value = re.sub(r"[\s-]", "", self.cleaned_data["phone"])
        if not PHONE_RE.match(value):
            raise ValidationError("Enter a valid phone number.")
        if User.objects.filter(phone=value).exists():
            raise ValidationError("An account with this phone number already exists.")
        return value

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        elif password:
            temp = User(email=data.get("email"), phone=data.get("phone"))
            try:
                password_validation.validate_password(password, temp)
                if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
                    raise ValidationError("Password must contain at least one letter and one digit.")
            except ValidationError as e:
                self.add_error("password", e)
        return data

    def save(self):
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    email=self.cleaned_data["email"],
                    phone=self.cleaned_data["phone"],
                    password=self.cleaned_data["password"],
                )
        except IntegrityError:
            if User.objects.filter(email__iexact=self.cleaned_data["email"]).exists():
                self.add_error("email", "An account with this email already exists.")
            if User.objects.filter(phone=self.cleaned_data["phone"]).exists():
                self.add_error("phone", "An account with this phone number already exists.")
            return None


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Invalid credentials. Please try again.",
        "inactive": "Invalid credentials. Please try again.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email or phone"

    def clean(self):
        username, password = self.cleaned_data.get("username"), self.cleaned_data.get("password")
        if not username or not password:
            return super().clean()
        key = throttle.key_for(username)
        minutes = throttle.minutes_locked(key)
        if minutes:
            raise ValidationError(throttle.lock_message(minutes), code="locked")
        try:
            cleaned = super().clean()
        except ValidationError:
            minutes = throttle.record_failure(key)
            if minutes:
                raise ValidationError(throttle.lock_message(minutes), code="locked")
            raise
        throttle.reset(key)
        return cleaned


class PasswordResetRequestForm(forms.Form):
    identifier = forms.CharField(label="Email or phone number", max_length=254)

    def get_user(self):
        value = self.cleaned_data["identifier"].strip()
        if "@" in value:
            return User.objects.filter(email__iexact=value, is_active=True).first()
        return User.objects.filter(phone=re.sub(r"[\s-]", "", value), is_active=True).first()


class SetNewPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, strip=False, label="New password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, strip=False)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        elif password:
            try:
                password_validation.validate_password(password, self.user)
                if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
                    raise ValidationError("Password must contain at least one letter and one digit.")
            except ValidationError as e:
                self.add_error("password", e)
        return data

    def save(self):
        self.user.set_password(self.cleaned_data["password"])
        self.user.save(update_fields=["password"])
        return self.user


class PasswordResetOTPForm(forms.Form):
    """Enter the six digit code emailed with the reset link (Test Plan FR-14_UT02)."""

    identifier = forms.CharField(label="Email or phone number", max_length=254)
    code = forms.RegexField(
        r"^[0-9]{6}$", max_length=6, label="Six digit code",
        error_messages={"invalid": "Enter the six digit code from the email."},
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )

    def get_user(self):
        value = self.cleaned_data["identifier"].strip()
        if "@" in value:
            return User.objects.filter(email__iexact=value, is_active=True).first()
        return User.objects.filter(phone=re.sub(r"[\s-]", "", value), is_active=True).first()
