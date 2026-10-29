from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate with either the email (case-insensitive) or the phone number."""

    def user_can_authenticate(self, user):
        # is_active is the primary switch; the timestamps are a second guard so a
        # manually reactivated suspended/removed row still cannot sign in.
        return super().user_can_authenticate(user) and not user.is_suspended and not user.is_removed

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username or password is None:
            return None
        User = get_user_model()
        identifier = username.strip()
        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(phone=identifier).first()
        )
        if user is None:
            # Run the hasher anyway so timing does not reveal whether the account exists.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
