from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from catalog.models import Book, BookImage


class ListingEditRemoveTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=folder.name)
        override.enable()
        self.addCleanup(override.disable)
        permission = Permission.objects.get(codename="add_book", content_type__app_label="catalog")
        self.seller = User.objects.create_user("seller@example.com", "Reading2026!")
        self.other_seller = User.objects.create_user("other@example.com", "Reading2026!")
        for user in (self.seller, self.other_seller):
            user.user_permissions.add(permission)
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.book = Book.objects.create(
            title="The Hobbit",
            author="Tolkien",
            isbn="9780261103344",
            category="Fantasy",
            price="400",
            stock=2,
            seller=self.seller,
            status=Book.Status.APPROVED,
        )
        self.edit_url = reverse("listing_edit", args=[self.book.pk])
        self.remove_url = reverse("listing_remove", args=[self.book.pk])
        self.client.force_login(self.seller)

    def data(self, **changes):
        data = dict(
            title="The Hobbit (2nd ed.)",
            author="J.R.R. Tolkien",
            isbn="9780261103344",
            category="Adventure",
            price="450.50",
            condition="used",
            stock=7,
            description="Revised edition.",
        )
        data.update(changes)
        return data

    def upload(self, name="cover.png"):
        buf = BytesIO()
        Image.new("RGB", (40, 60), "green").save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    # --- edit ---
    def test_owner_sees_edit_form_with_current_values(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Hobbit")

    def test_owner_can_edit_every_field(self):
        response = self.client.post(self.edit_url, self.data())
        self.assertRedirects(response, reverse("seller_listings"))
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "The Hobbit (2nd ed.)")
        self.assertEqual(self.book.author, "J.R.R. Tolkien")
        self.assertEqual(self.book.category, "Adventure")
        self.assertEqual(str(self.book.price), "450.50")
        self.assertEqual(self.book.condition, "used")
        self.assertEqual(self.book.stock, 7)
        self.assertEqual(self.book.description, "Revised edition.")

    def test_edit_cannot_change_owner_or_status(self):
        self.client.post(self.edit_url, self.data(seller=self.buyer.pk, status="pending"))
        self.book.refresh_from_db()
        self.assertEqual(self.book.seller, self.seller)
        self.assertEqual(self.book.status, Book.Status.APPROVED)

    def test_invalid_edit_is_rejected_and_nothing_changes(self):
        for changes in ({"title": ""}, {"price": "0"}, {"isbn": "123"}, {"stock": "-1"}):
            with self.subTest(changes=changes):
                response = self.client.post(self.edit_url, self.data(**changes))
                self.assertEqual(response.status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "The Hobbit")
        self.assertEqual(self.book.stock, 2)

    def test_add_and_remove_images(self):
        self.client.post(self.edit_url, self.data(images=[self.upload("a.png"), self.upload("b.png")]))
        self.assertEqual(self.book.images.count(), 2)
        first = self.book.images.first()
        self.client.post(self.edit_url, self.data(remove_images=[first.pk]))
        self.assertEqual(self.book.images.count(), 1)
        self.assertFalse(BookImage.objects.filter(pk=first.pk).exists())

    def test_total_images_are_capped_at_five(self):
        self.client.post(self.edit_url, self.data(images=[self.upload(f"{n}.png") for n in range(4)]))
        response = self.client.post(self.edit_url, self.data(images=[self.upload("x.png"), self.upload("y.png")]))
        self.assertContains(response, "at most five images")
        self.assertEqual(self.book.images.count(), 4)

    def test_edit_cannot_remove_another_listings_image(self):
        other = Book.objects.create(title="Other", author="A", isbn="9780132350884", price=10, seller=self.other_seller)
        image = BookImage.objects.create(book=other, image=self.upload())
        response = self.client.post(self.edit_url, self.data(remove_images=[image.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(BookImage.objects.filter(pk=image.pk).exists())

    def test_other_sellers_cannot_edit_a_listing(self):
        self.client.force_login(self.other_seller)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 404)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "The Hobbit")

    def test_edit_requires_login_and_seller_permission(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.edit_url), f"{reverse('login')}?next={self.edit_url}")
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 403)

    def test_unknown_listing_is_not_found(self):
        self.assertEqual(self.client.get(reverse("listing_edit", args=[999999])).status_code, 404)

    # --- remove ---
    def test_remove_asks_for_confirmation_and_changes_nothing_on_get(self):
        response = self.client.get(self.remove_url)
        self.assertContains(response, "Remove")
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.APPROVED)

    def test_removed_listing_disappears_from_search_detail_and_seller_list(self):
        self.assertContains(self.client.get(reverse("catalog"), {"q": "Hobbit"}), "The Hobbit")
        response = self.client.post(self.remove_url)
        self.assertRedirects(response, reverse("seller_listings"))
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.REMOVED)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())
        self.assertNotContains(self.client.get(reverse("catalog"), {"q": "Hobbit"}), "The Hobbit")
        self.assertEqual(self.client.get(reverse("book_detail", args=[self.book.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("seller_listings")), "The Hobbit")

    def test_removed_listing_cannot_be_edited_or_removed_again(self):
        self.client.post(self.remove_url)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.remove_url).status_code, 404)

    def test_other_sellers_cannot_remove_a_listing(self):
        self.client.force_login(self.other_seller)
        self.assertEqual(self.client.get(self.remove_url).status_code, 404)
        self.assertEqual(self.client.post(self.remove_url).status_code, 404)
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.APPROVED)

    def test_remove_requires_login_and_seller_permission(self):
        self.client.logout()
        self.assertRedirects(self.client.post(self.remove_url), f"{reverse('login')}?next={self.remove_url}")
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(self.remove_url).status_code, 403)
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.APPROVED)

    def test_remove_rejects_other_http_methods(self):
        self.assertEqual(self.client.put(self.remove_url).status_code, 405)

    def test_remove_needs_csrf_token(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(client.post(self.remove_url).status_code, 403)
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.APPROVED)

    def test_seller_list_links_to_edit_and_remove(self):
        response = self.client.get(reverse("seller_listings"))
        self.assertContains(response, self.edit_url)
        self.assertContains(response, self.remove_url)
