from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from reviews.models import Review


class BookDetailTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(
            title="Clean Code",
            author="Robert C. Martin",
            isbn="9780132350884",
            description="A handbook of agile craftsmanship.",
            price=Decimal("799.00"),
            stock=4,
        )

    def get(self, book=None):
        return self.client.get(reverse("book_detail", args=[(book or self.book).pk]))

    def test_shows_core_details(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        for text in ("Clean Code", "Robert C. Martin", "9780132350884", "799.00", "In stock", "agile craftsmanship"):
            self.assertContains(response, text)

    def test_seller_and_condition_fall_back_when_not_set(self):
        response = self.get()
        self.assertContains(response, "Not specified")

    def test_out_of_stock_is_marked_and_cannot_be_added(self):
        self.book.stock = 0
        self.book.save()
        response = self.get()
        self.assertContains(response, "Out of stock")
        self.assertContains(response, "disabled")
        self.assertNotContains(response, "Add to cart")

    def test_in_stock_shows_add_to_cart(self):
        self.assertContains(self.get(), "Add to cart")

    def test_average_rating_and_reviews(self):
        first = User.objects.create_user("a@example.com", "pw", full_name="Asha")
        second = User.objects.create_user("b@example.com", "pw")
        Review.objects.create(book=self.book, user=first, rating=5, comment="Great read")
        Review.objects.create(book=self.book, user=second, rating=2)
        response = self.get()
        self.assertContains(response, "3.5 / 5 (2 reviews)")
        self.assertContains(response, "Great read")
        self.assertContains(response, "Asha")
        self.assertContains(response, "A reader")

    def test_reviewer_contact_details_are_not_exposed(self):
        user = User.objects.create_user("private@example.com", "pw", phone="+15550999")
        Review.objects.create(book=self.book, user=user, rating=4)
        response = self.get()
        self.assertNotContains(response, "private@example.com")
        self.assertNotContains(response, "+15550999")

    def test_no_reviews_message(self):
        response = self.get()
        self.assertContains(response, "No ratings yet")
        self.assertContains(response, "No reviews yet")

    def test_user_content_is_escaped(self):
        self.book.title = "<script>alert(1)</script>"
        self.book.save()
        response = self.get()
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_unapproved_listing_is_hidden(self):
        self.book.status = "pending"
        self.assertEqual(getattr(self.book, "status"), "pending")
        from unittest import mock

        with mock.patch("catalog.views.get_object_or_404", return_value=self.book):
            self.assertEqual(self.get().status_code, 404)

    @override_settings(DEBUG=False)
    def test_unknown_book_shows_not_found_page(self):
        response = self.client.get(reverse("book_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_catalogue_links_to_detail_page(self):
        response = self.client.get(reverse("catalog"))
        self.assertContains(response, reverse("book_detail", args=[self.book.pk]))
