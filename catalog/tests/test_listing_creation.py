from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from catalog.forms import ListingForm
from catalog.models import Book, BookImage

class ListingCreationTests(TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override=override_settings(MEDIA_ROOT=self.folder.name)
        self.override.enable();self.addCleanup(self.override.disable)
        self.seller=User.objects.create_user("seller@example.com","Reading2026!")
        self.seller.user_permissions.add(Permission.objects.get(codename="add_book",content_type__app_label="catalog"))
        self.buyer=User.objects.create_user("buyer@example.com","Reading2026!")
        self.client.force_login(self.seller)

    def data(self, **changes):
        data=dict(title="A New Book",author="Tolkien",isbn="9780261103344",category="Fantasy",price="400",condition="new",stock=5,description="A story.")
        data.update(changes);return data

    def upload(self,name="cover.png"):
        buf=BytesIO();Image.new("RGB",(40,60),"green").save(buf,format="PNG")
        return SimpleUploadedFile(name,buf.getvalue(),content_type="image/png")

    def test_add_multiple_images_and_ignore_spoofed_owner_and_status(self):
        self.assertEqual(self.client.get(reverse("listing_add")).status_code,200)
        r=self.client.post(reverse("listing_add"),self.data(images=[self.upload(),self.upload("two.png")],seller=self.buyer.pk,status="approved"))
        self.assertRedirects(r,reverse("seller_listings"))
        book=Book.objects.get()
        self.assertEqual(book.seller,self.seller);self.assertEqual(book.status,"pending")
        self.assertEqual(book.images.count(),2)
        self.assertTrue(book.cover_url.endswith(".png"))
        self.assertNotContains(self.client.get(reverse("catalog")),book.title)
        book.status="approved";book.save(update_fields=["status"])
        self.assertContains(self.client.get(reverse("catalog")),book.title)
        self.assertContains(self.client.get(reverse("catalog")),book.cover_url)

    def test_listing_without_optional_images_and_isbn10(self):
        self.client.post(reverse("listing_add"),self.data(isbn="0261103342"))
        book=Book.objects.get();self.assertEqual(book.cover_url,"")
        self.assertEqual(book.isbn,"0261103342")
        self.assertEqual(book.images.count(),0)

    def test_unauthorized_and_csrf(self):
        self.client.logout()
        r=self.client.get(reverse("listing_add"));self.assertEqual(r.status_code,302)
        self.assertIn("/accounts/login/",r.url)
        self.client.force_login(self.buyer)
        for url in [reverse("listing_add"),reverse("seller_listings")]:self.assertEqual(self.client.get(url).status_code,403)
        c=Client(enforce_csrf_checks=True);c.force_login(self.seller)
        self.assertEqual(c.post(reverse("listing_add"),self.data()).status_code,403)
        self.assertFalse(Book.objects.exists())

    def test_invalid_required_values_do_not_persist(self):
        for changes in [dict(title=""),dict(author=""),dict(price=""),dict(price="-1"),dict(stock="-1"),dict(condition="damaged"),dict(category=""),dict(isbn="123"),dict(isbn="9780261103345")]:
            with self.subTest(changes=changes):
                r=self.client.post(reverse("listing_add"),self.data(**changes))
                self.assertEqual(r.status_code,200);self.assertTrue(r.context["form"].errors)
        self.assertEqual(Book.objects.count(),0)

    def test_invalid_and_excessive_images_do_not_persist(self):
        payloads=[
            [SimpleUploadedFile("bad.svg",b"<svg><script/></svg>",content_type="image/svg+xml")],
            [SimpleUploadedFile("bad.png",b"broken",content_type="image/png")],
            [SimpleUploadedFile("big.png",b"x"*(2*1024*1024+1),content_type="image/png")],
            [self.upload(f"{n}.png") for n in range(6)],
        ]
        for images in payloads:
            with self.subTest(names=[f.name for f in images]):
                r=self.client.post(reverse("listing_add"),self.data(images=images))
                self.assertTrue(r.context["form"].errors)
        self.assertEqual(Book.objects.count(),0);self.assertEqual(BookImage.objects.count(),0)

    def test_publication_and_owned_list_separation(self):
        own=Book.objects.create(seller=self.seller,title="Visible",author="A",isbn="9780261103344",price=1,status="approved")
        Book.objects.create(seller=self.buyer,title="Other private listing",author="A",isbn="9780261103344",price=1,status="pending")
        r=self.client.get(reverse("seller_listings"));self.assertContains(r,"Visible");self.assertNotContains(r,"Other private listing")
        for status in ["pending","suspended","removed"]:
            own.status=status;own.save()
            self.assertNotContains(self.client.get(reverse("catalog")),"Visible")
        own.status="approved";own.save();self.seller.is_active=False;self.seller.save()
        self.assertNotContains(self.client.get(reverse("catalog")),"Visible")

    def test_non_ascii_isbn_returns_validation_error(self):
        for isbn in ("²" * 13, "²" * 9 + "X", "٩" * 13):
            with self.subTest(isbn=isbn):
                response = self.client.post(reverse("listing_add"), self.data(isbn=isbn))
                self.assertEqual(response.status_code, 200)
                self.assertFormError(response.context["form"], "isbn", "Enter a valid ISBN-10 or ISBN-13, including its check digit.")
        self.assertFalse(Book.objects.exists())
