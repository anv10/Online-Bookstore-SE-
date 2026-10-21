from django.test import TestCase
from django.urls import reverse
from catalog.models import Book
from accounts.models import User

class FilterTests(TestCase):
    def setUp(self):
        self.seller=User.objects.create_user("fixture@example.com","Fixture2026!")
        for n,(title,genre,price) in enumerate([("Clean Code","Technology",799),("Deep Work","Productivity",400),("Clean Architecture","Technology",600),("Dune","Fantasy",300)]):
            Book.objects.create(seller=self.seller,status="approved",title=title,author="A",isbn=f"{n:013}",category=genre,price=price)

    def query(self, **params):
        return self.client.get(reverse("catalog"),params)

    def test_multigenre_and_price_combinations(self):
        r=self.query(genre=["Technology","Productivity"],min_price="400",max_price="600")
        self.assertEqual({b.title for b in r.context["page_obj"]},{"Deep Work","Clean Architecture"})
        r=self.query(q="Clean",genre=["Technology"],min_price="600",max_price="600")
        self.assertEqual([b.title for b in r.context["page_obj"]],["Clean Architecture"])
        self.assertEqual(self.query(min_price="0").context["page_obj"].paginator.count,4)
        self.assertEqual(self.query().context["page_obj"].paginator.count,4)

    def test_invalid_ranges_and_values(self):
        for params in [dict(min_price="10",max_price="1"),dict(min_price="-1"),dict(max_price="NaN"),dict(min_price="Infinity"),dict(genre=["Unknown"]),dict(max_price="1000000000")]:
            with self.subTest(params=params):
                r=self.query(**params);self.assertTrue(r.context["form"].errors)
                self.assertEqual(r.context["page_obj"].paginator.count,0)

    def test_pagination_preserves_multiple_filters(self):
        for n in range(12):Book.objects.create(seller=self.seller,status="approved",title=f"Added {n}",author="A",isbn=f"99{n:011}",category="Technology",price=650)
        r=self.query(genre=["Technology","Productivity"],min_price="400",page="2")
        query=r.context["query"]
        self.assertIn("genre=Technology",query);self.assertIn("genre=Productivity",query)
        self.assertIn("min_price=400",query);self.assertNotIn("page=",query)
        self.assertContains(r,'Clear filters')
