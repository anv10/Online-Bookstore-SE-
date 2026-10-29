from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order
from .notifications import queue_confirmation


@receiver(post_save, sender=Order, dispatch_uid="orders.send_confirmation_email")
def send_confirmation_after_commit(sender, instance, created, **kwargs):
    if created:
        # After commit, so the items exist and a rolled-back order sends nothing.
        transaction.on_commit(partial(queue_confirmation, instance.pk), robust=True)
