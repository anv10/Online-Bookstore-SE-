from django.core.management.base import BaseCommand

from orders.models import OrderConfirmation
from orders.notifications import send_confirmation


class Command(BaseCommand):
    help = "Send order confirmation emails that have not gone out yet (run it from cron)."

    def handle(self, *args, **options):
        sent = 0
        pending = OrderConfirmation.objects.filter(state=OrderConfirmation.State.PENDING).order_by("pk")
        for confirmation in pending:
            if send_confirmation(confirmation):
                sent += 1
        still_pending = OrderConfirmation.objects.filter(state=OrderConfirmation.State.PENDING).count()
        failed = OrderConfirmation.objects.filter(state=OrderConfirmation.State.FAILED).count()
        self.stdout.write(f"Sent {sent}, still pending {still_pending}, given up {failed}.")
