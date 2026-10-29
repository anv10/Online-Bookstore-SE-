from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from catalog.models import Book


class SupportChannelTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "pw")
        self.book = Book.objects.create(
            title="Clean Code",
            author="Robert Martin",
            isbn="9780132350884",
            price=Decimal("500"),
            stock=2,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )

    def test_support_page_is_public_and_shows_the_email_channel(self):
        response = self.client.get(reverse("support"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "support@chapterandco.example")
        self.assertContains(response, "mailto:support@chapterandco.example")
        self.assertContains(response, "within 24 hours")

    def test_footer_links_to_support_on_public_and_private_pages(self):
        pages = [
            reverse("catalog"),
            reverse("book_detail", args=[self.book.pk]),
            reverse("login"),
            reverse("register"),
            reverse("support"),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), reverse("support"))
        self.client.force_login(self.seller)
        for url in (reverse("profile"), reverse("cart"), reverse("order_list")):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), reverse("support"))

    @override_settings(SUPPORT_EMAIL="help@bookstore.test")
    def test_configured_support_address_is_used(self):
        response = self.client.get(reverse("support"))
        self.assertContains(response, "help@bookstore.test")
        self.assertContains(response, "mailto:help@bookstore.test")

    def test_support_page_does_not_leak_private_account_details(self):
        response = self.client.get(reverse("support"))
        self.assertNotContains(response, "seller@example.com")
