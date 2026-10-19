from django.test import TestCase
from django.urls import reverse
from catalog.models import Book

class SearchTests(TestCase):
    def setUp(self):
        self.book=Book.objects.create(title="Clean Code",author="Robert C. Martin",isbn="9780132350884",category="Technology",price="799",stock=4)
        Book.objects.create(title="The Hobbit",author="Tolkien",isbn="9780261103344",category="Fantasy",price="400",stock=2)

    def test_search_title_author_and_exact_isbn(self):
        for query in ["clean", "MARTIN", self.book.isbn]:
            with self.subTest(query=query):
                r=self.client.get(reverse("catalog"),{"q":query})
                self.assertEqual(list(r.context["page_obj"]),[self.book])
        self.assertEqual(self.client.get(reverse("catalog"),{"q":"013235"}).context["page_obj"].paginator.count,0)

    def test_empty_query_and_no_results(self):
        self.assertContains(self.client.get(reverse("catalog"),{"q":""}),"Enter a search term")
        self.assertContains(self.client.get(reverse("catalog"),{"q":"9780000000000"}),"No books found")
        self.assertContains(self.client.get(reverse("catalog"),{"q":"' OR 1=1 --"}),"No books found")
        self.assertTrue(self.client.get(reverse("catalog"),{"q":"x"*256}).context["form"].errors)

    def test_pagination_and_query_persistence(self):
        for n in range(12):Book.objects.create(title=f"Clean title {n:02}",author="A",isbn=f"{n:013}",price=10)
        r=self.client.get(reverse("catalog"),{"q":"Clean","page":"2"})
        self.assertEqual(len(r.context["page_obj"]),4)
        self.assertEqual(r.context["query"],"q=Clean")
        self.assertEqual(self.client.get(reverse("catalog"),{"page":"invalid"}).status_code,200)
        self.assertEqual(self.client.get(reverse("catalog"),{"page":"999"}).status_code,200)

    def test_user_content_is_escaped(self):
        self.book.title="<script>alert(1)</script>";self.book.save()
        r=self.client.get(reverse("catalog"))
        self.assertNotContains(r,"<script>alert(1)</script>")
        self.assertContains(r,"&lt;script&gt;")
