import re

from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from django.db import IntegrityError, transaction

from .models import User

PHONE_RE = re.compile(r"^\+?\d{7,15}$")


class RegistrationForm(forms.Form):
    identifier = forms.CharField(label="Email or phone number", max_length=254)
    password = forms.CharField(widget=forms.PasswordInput, strip=False)
    confirm_password = forms.CharField(widget=forms.PasswordInput, strip=False)

    def clean_identifier(self):
        value = self.cleaned_data["identifier"].strip()
        if "@" in value:
            forms.EmailField().clean(value)
            value = value.lower()
            if User.objects.filter(email__iexact=value).exists():
                raise ValidationError("An account with this email already exists.")
            self.kind = "email"
        else:
            value = re.sub(r"[\s-]", "", value)
            if not PHONE_RE.match(value):
                raise ValidationError("Enter a valid email address or phone number.")
            if User.objects.filter(phone=value).exists():
                raise ValidationError("An account with this phone number already exists.")
            self.kind = "phone"
        return value

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        elif password:
            temp = User(**{getattr(self, "kind", "email"): data.get("identifier")})
            try:
                password_validation.validate_password(password, temp)
                if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
                    raise ValidationError("Password must contain at least one letter and one digit.")
            except ValidationError as e:
                self.add_error("password", e)
        return data

    def save(self):
        ident = self.cleaned_data["identifier"]
        password = self.cleaned_data["password"]
        try:
            with transaction.atomic():
                if self.kind == "email":
                    return User.objects.create_user(email=ident, password=password)
                return User.objects.create_user(password=password, phone=ident)
        except IntegrityError:
            label = "email" if self.kind == "email" else "phone number"
            self.add_error("identifier", f"An account with this {label} already exists.")
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
