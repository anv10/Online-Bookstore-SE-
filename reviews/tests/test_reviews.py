from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Book
from orders.models import Order, OrderItem
from reviews.models import Review


class ReviewSubmissionTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!", full_name="Asha Rao")
        self.other = User.objects.create_user("other@example.com", "Reading2026!")
        self.book = self.make_book()
        self.client.force_login(self.buyer)

    def make_book(self, **changes):
        values = dict(
            title="Clean Code",
            author="Robert Martin",
            isbn="9780132350884",
            price=Decimal("500"),
            stock=5,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        values.update(changes)
        return Book.objects.create(**values)

    def deliver(self, *books, user=None, status=Order.Status.DELIVERED):
        order = Order.objects.create(
            user=user or self.buyer,
            total=Decimal("500") * len(books or [self.book]),
            status=status,
            shipping_address="12 Main Road",
        )
        for book in books or (self.book,):
            OrderItem.objects.create(order=order, book=book, quantity=1, unit_price=book.price)
        return order

    def url(self, book=None):
        return reverse("review_submit", args=[(book or self.book).pk])

    def post(self, **data):
        payload = {"rating": 5, "comment": "Loved it"}
        payload.update(data)
        return self.client.post(self.url(), payload)

    # --- eligibility ---
    def test_only_a_delivered_purchase_can_be_reviewed(self):
        for status in (Order.Status.PENDING, Order.Status.PAID, Order.Status.SHIPPED):
            with self.subTest(status=status):
                order = self.deliver(status=status)
                response = self.post()
                self.assertRedirects(
                    response, reverse("book_detail", args=[self.book.pk]), fetch_redirect_response=False
                )
                self.assertContains(self.client.get(response.url), "must purchase this book")
                self.assertFalse(Review.objects.exists())
                order.delete()

    def test_delivered_purchase_can_be_reviewed(self):
        self.deliver()
        response = self.post(rating=4, comment="Clear and useful")
        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        review = Review.objects.get()
        self.assertEqual((review.book, review.user, review.rating, review.comment), (self.book, self.buyer, 4, "Clear and useful"))

    def test_someone_elses_delivered_order_does_not_count(self):
        self.deliver(user=self.other)
        self.post()
        self.assertFalse(Review.objects.exists())

    def test_delivered_order_for_another_book_does_not_count(self):
        other_book = self.make_book(title="Refactoring", isbn="9780201485677")
        self.deliver(other_book)
        self.post()
        self.assertFalse(Review.objects.exists())

    def test_review_text_is_optional(self):
        self.deliver()
        self.post(rating=3, comment="")
        self.assertEqual(Review.objects.get().comment, "")

    def test_book_must_be_visible(self):
        hidden = self.make_book(title="Hidden", isbn="9780000000011", status=Book.Status.PENDING)
        self.deliver(hidden)
        self.assertEqual(self.client.post(self.url(hidden), {"rating": 5}).status_code, 404)

    def test_unknown_book_is_not_found(self):
        self.assertEqual(self.client.post(reverse("review_submit", args=[999999]), {"rating": 5}).status_code, 404)

    # --- validation and editing ---
    def test_rating_outside_one_to_five_is_rejected(self):
        self.deliver()
        for bad in ("0", "6", "", "abc"):
            with self.subTest(rating=bad):
                response = self.post(rating=bad)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Rating must be between 1 and 5.")
                self.assertFalse(Review.objects.exists())

    def test_review_is_editable_and_stays_a_single_row(self):
        self.deliver()
        self.post(rating=2, comment="Not for me")
        response = self.post(rating=5, comment="Changed my mind")
        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        review = Review.objects.get()
        self.assertEqual((review.rating, review.comment), (5, "Changed my mind"))

    def test_edit_form_is_shown_to_the_buyer_who_reviewed(self):
        self.deliver()
        self.post()
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "Edit your review")
        self.assertNotContains(page, "Write a review")

    def test_form_is_only_linked_after_a_delivered_purchase(self):
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "after an order containing it is delivered")
        self.assertNotContains(page, "Write a review")
        response = self.client.get(self.url())
        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))

    def test_get_form_works_for_eligible_buyer(self):
        self.deliver()
        response = self.client.get(self.url())
        self.assertContains(response, "RATE THIS BOOK")
        self.assertContains(response, self.book.title)

    def test_anonymous_users_are_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url()), f"{reverse('login')}?next={self.url()}")
        self.assertRedirects(self.client.post(self.url()), f"{reverse('login')}?next={self.url()}")

    def test_post_needs_csrf(self):
        self.deliver()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.buyer)
        self.assertEqual(strict.post(self.url(), {"rating": 5}).status_code, 403)
        self.assertFalse(Review.objects.exists())

    # --- averages and visibility ---
    def test_average_rating_updates_on_the_detail_page(self):
        for user, rating in ((self.buyer, 4), (self.other, 5)):
            Review.objects.create(book=self.book, user=user, rating=rating)
        self.assertEqual(self.client.get(reverse("book_detail", args=[self.book.pk])).context["average_rating"], 4.5)
        third = User.objects.create_user("third@example.com", "pw")
        Review.objects.create(book=self.book, user=third, rating=3)
        self.assertContains(self.client.get(reverse("book_detail", args=[self.book.pk])), "4.0 / 5 (3 reviews)")

    def test_review_is_visible_to_other_buyers(self):
        self.deliver()
        self.post(rating=5, comment="Everyone should read this")
        self.client.force_login(self.other)
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "Everyone should read this")
        self.assertContains(page, "Asha Rao")

    def test_admin_removal_recalculates_the_average(self):
        Review.objects.create(book=self.book, user=self.buyer, rating=5)
        bad = Review.objects.create(book=self.book, user=self.other, rating=1)
        admin = User.objects.create_superuser("admin@example.com", "pw")
        self.client.force_login(admin)
        response = self.client.post(
            reverse("admin:reviews_review_delete", args=[bad.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.filter(pk=bad.pk).exists())
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertContains(page, "5.0 / 5 (1 review)")

    def test_review_html_is_escaped(self):
        self.deliver()
        self.post(rating=5, comment="<script>alert(1)</script>")
        page = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")
