from django.core.management.base import BaseCommand

from orders.models import OrderConfirmation
from orders.notifications import send_confirmation, send_sms_confirmation


class Command(BaseCommand):
    help = "Send order confirmation emails and SMS that have not gone out yet (run it from cron)."

    def handle(self, *args, **options):
        State = OrderConfirmation.State
        sent = 0
        for confirmation in OrderConfirmation.objects.filter(state=State.PENDING).order_by("pk"):
            if send_confirmation(confirmation):
                sent += 1
        still_pending = OrderConfirmation.objects.filter(state=State.PENDING).count()
        failed = OrderConfirmation.objects.filter(state=State.FAILED).count()
        self.stdout.write(f"Sent {sent}, still pending {still_pending}, given up {failed}.")
        sms_sent = 0
        for confirmation in OrderConfirmation.objects.filter(sms_state=State.PENDING).order_by("pk"):
            if send_sms_confirmation(confirmation):
                sms_sent += 1
        sms_pending = OrderConfirmation.objects.filter(sms_state=State.PENDING).count()
        sms_failed = OrderConfirmation.objects.filter(sms_state=State.FAILED).count()
        self.stdout.write(f"SMS: sent {sms_sent}, still pending {sms_pending}, given up {sms_failed}.")
