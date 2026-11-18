from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from . import events


def _masked(identifier):
    identifier = (identifier or "").strip()
    return f"{identifier[:2]}***" if identifier else ""


@receiver(user_logged_in)
def _logged_in(sender, request, user, **kwargs):
    events.record(events.Kind.LOGIN_SUCCESS, request, user=user)


@receiver(user_login_failed)
def _login_failed(sender, credentials, request=None, **kwargs):
    # The password is never recorded; the identifier is masked (SEC-18).
    events.record(events.Kind.LOGIN_FAILED, request, user=None, detail=f"identifier={_masked(credentials.get('username'))}")


@receiver(user_logged_out)
def _logged_out(sender, request, user, **kwargs):
    if user is not None:
        events.record(events.Kind.LOGOUT, request, user=user)
