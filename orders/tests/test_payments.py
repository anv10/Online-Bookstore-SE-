from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from orders import payments


class CardValidationTests(SimpleTestCase):
    def test_spaces_and_dashes_are_ignored(self):
        self.assertEqual(payments.clean_number("4242-4242 4242 4242"), "4242424242424242")

    def test_valid_lengths_and_check_digit_are_accepted(self):
        self.assertEqual(payments.clean_number("4242424242424242"), "4242424242424242")
        self.assertEqual(payments.clean_number("4111111111111111"), "4111111111111111")

    def test_short_numeric_cards_are_rejected(self):
        with self.assertRaisesMessage(payments.PaymentError, "Invalid card number."):
            payments.clean_number("1234")

    def test_failed_check_digit_is_rejected(self):
        with self.assertRaisesMessage(payments.PaymentError, "Invalid card number."):
            payments.clean_number("4242424242424241")

    def test_non_numeric_cards_are_rejected(self):
        with self.assertRaisesMessage(payments.PaymentError, "Invalid card number."):
            payments.clean_number("abcd efgh ijkl mnop")

    def test_future_expiry_is_accepted(self):
        self.assertEqual(payments.clean_expiry("12/34"), "12/34")

    def test_past_expiry_is_rejected(self):
        past = f"01/{date.today().year - 1 - 2000:02d}"
        with self.assertRaisesMessage(payments.PaymentError, "Invalid expiry date."):
            payments.clean_expiry(past)

    def test_malformed_expiry_is_rejected(self):
        for raw in ("", "2030", "13/30", "00/30", "aa/bb"):
            with self.subTest(expiry=raw):
                with self.assertRaisesMessage(payments.PaymentError, "Invalid expiry date."):
                    payments.clean_expiry(raw)

    def test_three_or_four_digit_security_codes_are_accepted(self):
        self.assertEqual(payments.clean_cvc("123"), "123")
        self.assertEqual(payments.clean_cvc("1234"), "1234")

    def test_bad_security_codes_are_rejected(self):
        for raw in ("", "12", "12345", "abc"):
            with self.subTest(cvc=raw):
                with self.assertRaisesMessage(payments.PaymentError, "Invalid security code."):
                    payments.clean_cvc(raw)


class SandboxGatewayTests(SimpleTestCase):
    def setUp(self):
        self.card = payments.CardDetails("4242424242424242", "12/34", "123")

    def test_valid_card_is_charged_with_a_reference(self):
        result = payments.SandboxGateway().charge(self.card, Decimal("100.00"))
        self.assertTrue(result.success)
        self.assertTrue(result.reference.startswith("SBX-"))

    def test_decline_card_is_refused_without_a_reference(self):
        card = payments.CardDetails("4000000000000002", "12/34", "123")
        result = payments.SandboxGateway().charge(card, Decimal("100.00"))
        self.assertFalse(result.success)
        self.assertIn("declined", result.error)
        self.assertEqual(result.reference, "")

    def test_last_four_digits_are_available_without_the_full_number(self):
        self.assertEqual(self.card.last4, "4242")

    def test_sandbox_is_the_configured_gateway(self):
        self.assertIsInstance(payments.get_gateway(), payments.SandboxGateway)

    @override_settings(PAYMENT_GATEWAY="unconfigured")
    def test_unknown_gateway_is_reported(self):
        with self.assertRaisesMessage(payments.PaymentError, "Payments are not configured"):
            payments.get_gateway()
