from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class NavigationAuthLinksTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader@example.com", "s3cret-pass")

    def test_logged_out_visitor_sees_login_and_register(self):
        response = self.client.get(reverse("catalog"))
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, f'href="{reverse("register")}"')
        self.assertNotContains(response, "Log out")

    def test_logged_in_user_sees_logout_and_not_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("catalog"))
        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, "Log out")
        self.assertNotContains(response, f'href="{reverse("register")}"')

    def test_logout_button_ends_the_session(self):
        self.client.force_login(self.user)
        self.client.post(reverse("logout"))
        response = self.client.get(reverse("profile"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('profile')}")
