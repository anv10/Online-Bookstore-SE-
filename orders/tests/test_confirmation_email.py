import logging
from decimal import Decimal
from io import StringIO
from smtplib import SMTPException
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from cart.models import Cart, CartItem
from catalog.models import Book
from orders.models import Order, OrderConfirmation, OrderItem
from orders.notifications import MAX_ATTEMPTS, queue_confirmation, send_confirmation

ADDRESS = "12 Reading Lane, Bengaluru 560001, India"
CARD = {"card_number": "4242 4242 4242 4242", "card_expiry": "12/34", "card_cvc": "123"}


class ConfirmationEmailTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!", full_name="Asha Rao")
        self.book = self.make_book("Clean Code", "9780132350884", "400.00")
        self.second = self.make_book("The Hobbit", "9780261103344", "100.00")

    def make_book(self, title, isbn, price):
        return Book.objects.create(
            title=title, author="Author", isbn=isbn, price=Decimal(price), stock=9,
            seller=self.seller, status=Book.Status.APPROVED,
        )

    def place_order(self, user=None):
        """Create an order and its items in one transaction, the way checkout does."""
        from django.db import transaction

        with transaction.atomic():
            order = Order.objects.create(
                user=user or self.buyer, status=Order.Status.PAID, total=Decimal("1.00") + Decimal("900.00"),
                shipping_address=ADDRESS,
            )
            OrderItem.objects.create(order=order, book=self.book, quantity=2, unit_price=Decimal("400.00"))
            OrderItem.objects.create(order=order, book=self.second, quantity=1, unit_price=Decimal("100.00"))
        return order

    # --- sending ---
    def test_confirmation_is_sent_when_an_order_is_placed(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["buyer@example.com"])
        self.assertIn(f"#{order.pk}", message.subject)
        order.refresh_from_db()
        self.assertEqual(order.confirmation.state, OrderConfirmation.State.SENT)
        self.assertEqual(order.confirmation.attempts, 1)
        self.assertIsNotNone(order.confirmation.sent_at)

    def test_message_has_order_id_items_and_total(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        body = mail.outbox[0].body
        for text in (
            f"Order number: {order.pk}", "Clean Code x 2 at Rs 400.00 = Rs 800.00",
            "The Hobbit x 1 at Rs 100.00 = Rs 100.00", "Total: Rs 901.00",
        ):
            self.assertIn(text, body)

    def test_shipping_address_is_not_emailed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.place_order()
        self.assertNotIn("Reading Lane", mail.outbox[0].body)

    def test_nothing_is_sent_before_the_order_is_committed(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.place_order()
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_later_changes_to_the_order_do_not_send_it_again(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = Order.Status.SHIPPED
            order.save()
        self.assertEqual(len(mail.outbox), 1)

    def test_queueing_twice_sends_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        queue_confirmation(order.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(OrderConfirmation.objects.filter(order=order).count(), 1)

    def test_real_checkout_sends_the_confirmation(self):
        cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=cart, book=self.book, quantity=1)
        self.client.force_login(self.buyer)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("checkout"), {"shipping_address": ADDRESS, **CARD})
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_confirmation", args=[order.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Clean Code x 1", mail.outbox[0].body)

    # --- failures never block the order ---
    def test_a_failing_mail_server_does_not_block_the_order_and_is_logged(self):
        with mock.patch("orders.notifications.send_mail", side_effect=SMTPException("smtp.secret.example down")):
            with self.assertLogs("orders.notifications", level=logging.WARNING) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    order = self.place_order()
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        confirmation = OrderConfirmation.objects.get(order=order)
        self.assertEqual((confirmation.state, confirmation.attempts), (OrderConfirmation.State.PENDING, 1))
        self.assertEqual(confirmation.last_error, "SMTPException")
        output = "\n".join(logs.output)
        self.assertIn(f"order {order.pk}", output)
        self.assertNotIn("smtp.secret.example", output)
        self.assertNotIn("buyer@example.com", output)

    def test_a_backend_that_accepts_nothing_counts_as_a_failure(self):
        with mock.patch("orders.notifications.send_mail", return_value=0), self.assertLogs("orders.notifications"):
            with self.captureOnCommitCallbacks(execute=True):
                order = self.place_order()
        self.assertEqual(order.confirmation.state, OrderConfirmation.State.PENDING)
        self.assertEqual(order.confirmation.attempts, 1)

    def test_unexpected_errors_while_queueing_never_break_order_placement(self):
        with mock.patch.object(OrderConfirmation.objects, "get_or_create", side_effect=RuntimeError("boom")):
            with self.assertLogs("orders.notifications", level=logging.WARNING):
                with self.captureOnCommitCallbacks(execute=True):
                    order = self.place_order()
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(len(mail.outbox), 0)

    # --- retrying ---
    def fail_first_send(self):
        with mock.patch("orders.notifications.send_mail", side_effect=OSError), self.assertLogs("orders.notifications"):
            with self.captureOnCommitCallbacks(execute=True):
                return self.place_order()

    def test_retry_command_sends_pending_confirmations(self):
        order = self.fail_first_send()
        out = StringIO()
        call_command("retry_order_confirmations", stdout=out)
        order.confirmation.refresh_from_db()
        self.assertEqual(order.confirmation.state, OrderConfirmation.State.SENT)
        self.assertEqual(order.confirmation.attempts, 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Sent 1, still pending 0", out.getvalue())

    def test_retry_command_does_not_resend_sent_confirmations(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.place_order()
        call_command("retry_order_confirmations", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_retries_stop_after_the_maximum_attempts(self):
        order = self.fail_first_send()
        with mock.patch("orders.notifications.send_mail", side_effect=OSError), self.assertLogs("orders.notifications"):
            for _ in range(MAX_ATTEMPTS):
                call_command("retry_order_confirmations", stdout=StringIO())
        order.confirmation.refresh_from_db()
        self.assertEqual(order.confirmation.state, OrderConfirmation.State.FAILED)
        self.assertEqual(order.confirmation.attempts, MAX_ATTEMPTS)
        out = StringIO()
        call_command("retry_order_confirmations", stdout=out)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("given up 1", out.getvalue())

    def test_send_confirmation_ignores_finished_confirmations(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order()
        self.assertTrue(send_confirmation(order.confirmation))
        self.assertEqual(len(mail.outbox), 1)

    # --- buyers without an email address ---
    def test_buyers_without_an_email_are_skipped_not_retried(self):
        phone_only = User.objects.create_user(password="Reading2026!", phone="+15550123")
        with self.captureOnCommitCallbacks(execute=True):
            order = self.place_order(user=phone_only)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(order.confirmation.state, OrderConfirmation.State.SKIPPED)
        out = StringIO()
        call_command("retry_order_confirmations", stdout=out)
        self.assertIn("Sent 0, still pending 0", out.getvalue())
