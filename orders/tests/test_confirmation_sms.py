from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings

from accounts.models import User
from catalog.models import Book
from orders import sms
from orders.models import Order, OrderConfirmation, OrderItem
from orders.notifications import MAX_ATTEMPTS, send_sms_confirmation

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
State = OrderConfirmation.State


@override_settings(SMS_GATEWAY="console")
class ConfirmationSmsTests(TestCase):
    def setUp(self):
        sms.outbox.clear()
        self.addCleanup(sms.outbox.clear)
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!", phone="+15550123")
        self.book = Book.objects.create(
            title="Clean Code", author="Author", isbn="9780132350884", price=Decimal("400.00"), stock=9,
            seller=self.seller, status=Book.Status.APPROVED,
        )

    def place_order(self, user=None):
        with transaction.atomic():
            order = Order.objects.create(
                user=user or self.buyer, status=Order.Status.PAID, total=Decimal("825.00"), shipping_address=ADDRESS
            )
            OrderItem.objects.create(order=order, book=self.book, quantity=2, unit_price=Decimal("400.00"))
        return order

    def test_sms_is_sent_to_the_buyers_phone_when_an_order_is_placed(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        self.assertEqual(len(sms.outbox), 1)
        self.assertEqual(sms.outbox[0]["to"], "+15550123")
        order.refresh_from_db()
        self.assertEqual(order.confirmation.sms_state, State.SENT)
        self.assertEqual(order.confirmation.sms_attempts, 1)
        self.assertIsNotNone(order.confirmation.sms_sent_at)

    def test_text_has_order_id_copies_and_total_but_not_the_address(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        body = sms.outbox[0]["body"]
        self.assertIn(f"order #{order.pk}", body)
        self.assertIn("2 copies", body)
        self.assertIn("Rs 825.00", body)
        self.assertNotIn("Reading Lane", body)

    def test_single_copy_is_singular(self):
        order = self.place_order()
        order.items.update(quantity=1)
        self.assertIn("1 copy,", sms.confirmation_text(order))

    def test_email_and_sms_are_both_sent_and_tracked_separately(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        order.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(order.confirmation.state, State.SENT)
        self.assertEqual(order.confirmation.sms_state, State.SENT)

    def test_buyer_without_a_phone_is_skipped_not_retried(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order(user=self.seller)
        order.refresh_from_db()
        self.assertEqual(order.confirmation.sms_state, State.SKIPPED)
        self.assertEqual(order.confirmation.sms_last_error, "no phone number")
        self.assertEqual(sms.outbox, [])
        self.assertEqual(order.confirmation.state, State.SENT)

    def test_phone_only_buyer_gets_the_sms_and_no_email(self):
        phone_only = User.objects.create_user(password="Reading2026!", phone="+15550999")
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order(user=phone_only)
        order.refresh_from_db()
        self.assertEqual(order.confirmation.state, State.SKIPPED)
        self.assertEqual(order.confirmation.sms_state, State.SENT)
        self.assertEqual(sms.outbox[0]["to"], "+15550999")

    @override_settings(SMS_GATEWAY="")
    def test_switched_off_gateway_skips_sms(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        order.refresh_from_db()
        self.assertEqual(order.confirmation.sms_state, State.SKIPPED)
        self.assertEqual(order.confirmation.sms_last_error, "sms is switched off")
        self.assertEqual(order.confirmation.state, State.SENT)

    @override_settings(SMS_GATEWAY="unknown-provider")
    def test_unknown_gateway_is_a_logged_failure_that_does_not_block_the_order(self):
        with self.assertLogs("orders.notifications", level="WARNING"):
            with self.captureOnCommitCallbacks(execute=True):
                order = self.place_order()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.confirmation.sms_state, State.PENDING)
        self.assertEqual(order.confirmation.sms_attempts, 1)

    def test_failing_gateway_does_not_block_the_order_or_the_email_and_never_logs_the_phone(self):
        with mock.patch.object(sms.ConsoleGateway, "send", side_effect=ConnectionError("provider down +15550123")):
            with self.assertLogs("orders.notifications", level="WARNING") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    order = self.place_order()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.confirmation.state, State.SENT)
        self.assertEqual(order.confirmation.sms_state, State.PENDING)
        self.assertEqual(order.confirmation.sms_last_error, "ConnectionError")
        self.assertNotIn("15550123", "".join(logs.output))
        self.assertNotIn("provider down", "".join(logs.output))

    def test_a_failing_email_does_not_stop_the_sms(self):
        with mock.patch("orders.notifications.send_mail", side_effect=OSError("smtp down")):
            with self.assertLogs("orders.notifications", level="WARNING"):
                with self.captureOnCommitCallbacks(execute=True):
                    order = self.place_order()
        order.refresh_from_db()
        self.assertEqual(order.confirmation.state, State.PENDING)
        self.assertEqual(order.confirmation.sms_state, State.SENT)

    def test_retry_command_sends_pending_sms_and_does_not_resend_sent_ones(self):
        with mock.patch.object(sms.ConsoleGateway, "send", side_effect=ConnectionError("down")):
            with self.assertLogs("orders.notifications", level="WARNING"):
                with self.captureOnCommitCallbacks(execute=True):
                    order = self.place_order()
        self.assertEqual(sms.outbox, [])
        out = StringIO()
        call_command("retry_order_confirmations", stdout=out)
        self.assertIn("SMS: sent 1, still pending 0", out.getvalue())
        self.assertEqual(len(sms.outbox), 1)
        out = StringIO()
        call_command("retry_order_confirmations", stdout=out)
        self.assertIn("SMS: sent 0", out.getvalue())
        self.assertEqual(len(sms.outbox), 1)
        order.refresh_from_db()
        self.assertEqual(order.confirmation.sms_state, State.SENT)

    def test_sms_retries_stop_after_the_maximum_attempts(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        confirmation = order.confirmation
        confirmation.sms_state = State.PENDING
        confirmation.sms_attempts = 0
        confirmation.save()
        with mock.patch.object(sms.ConsoleGateway, "send", side_effect=ConnectionError("down")):
            with self.assertLogs("orders.notifications", level="WARNING"):
                for _ in range(MAX_ATTEMPTS + 2):
                    confirmation.refresh_from_db()
                    send_sms_confirmation(confirmation)
        confirmation.refresh_from_db()
        self.assertEqual(confirmation.sms_state, State.FAILED)
        self.assertEqual(confirmation.sms_attempts, MAX_ATTEMPTS)

    def test_finished_sms_confirmation_is_not_sent_again(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        confirmation = order.confirmation
        confirmation.refresh_from_db()
        self.assertTrue(send_sms_confirmation(confirmation))
        self.assertEqual(len(sms.outbox), 1)

    def test_console_gateway_logs_only_a_masked_number(self):
        with self.assertLogs("orders.sms", level="INFO") as logs:
            sms.ConsoleGateway().send("+15550123", "secret body text")
        line = "".join(logs.output)
        self.assertIn("...0123", line)
        self.assertNotIn("+15550123", line)
        self.assertNotIn("secret body", line)
