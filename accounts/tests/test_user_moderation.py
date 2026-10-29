from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import AccountAction, User
from catalog.models import Book
from orders.models import Order, OrderItem


class UserModerationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@example.com", "Reading2026!", full_name="Admin Person")
        self.grant_admin(self.admin)
        self.target = User.objects.create_user(
            "target@example.com", "Reading2026!", phone="+15550100", full_name="Asha Rao"
        )
        self.buyer = User.objects.create_user("buyer@example.com", "Reading2026!")
        self.client.force_login(self.admin)

    def grant_admin(self, user):
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        user.user_permissions.add(Permission.objects.get(codename="change_user", content_type__app_label="accounts"))
        return user

    def make_book(self, seller=None):
        return Book.objects.create(
            title="Clean Code",
            author="Robert Martin",
            isbn="9780132350884",
            price=Decimal("500"),
            stock=5,
            seller=seller or self.target,
            status=Book.Status.APPROVED,
        )

    def act(self, action="suspend", reason="Abusive behaviour", user=None):
        return self.client.post(
            reverse("user_admin_detail", args=[(user or self.target).pk]),
            {"action": action, "reason": reason},
        )

    def detail_url(self, user=None):
        return reverse("user_admin_detail", args=[(user or self.target).pk])

    # --- access ---
    def test_anonymous_users_are_sent_to_login(self):
        self.client.logout()
        for url in (reverse("user_admin_list"), self.detail_url()):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_buyers_and_sellers_are_denied(self):
        for user in (self.buyer, self.target):
            self.client.force_login(user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(reverse("user_admin_list")).status_code, 403)
                self.assertEqual(self.client.get(self.detail_url()).status_code, 403)
                self.assertEqual(self.act().status_code, 403)
        self.assertFalse(AccountAction.objects.exists())
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_staff_without_permission_and_permission_without_staff_are_denied(self):
        staff = User.objects.create_user("staff@example.com", "pw", is_staff=True)
        permitted = User.objects.create_user("permitted@example.com", "pw")
        permitted.user_permissions.add(Permission.objects.get(codename="change_user", content_type__app_label="accounts"))
        for user in (staff, permitted):
            self.client.force_login(user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(reverse("user_admin_list")).status_code, 403)
                self.assertEqual(self.act().status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_nav_link_is_only_shown_to_account_admins(self):
        self.assertContains(self.client.get(reverse("catalog")), reverse("user_admin_list"))
        self.client.force_login(self.buyer)
        self.assertNotContains(self.client.get(reverse("catalog")), reverse("user_admin_list"))

    # --- search ---
    def test_admin_can_search_by_email_phone_or_name(self):
        for query in ("target@", "+15550100", "Asha"):
            with self.subTest(query=query):
                response = self.client.get(reverse("user_admin_list"), {"q": query, "status": "all"})
                self.assertContains(response, "target@example.com")

    def test_search_and_status_filters_hide_non_matching_accounts(self):
        response = self.client.get(reverse("user_admin_list"), {"q": "nobody", "status": "all"})
        self.assertNotContains(response, "target@example.com")
        self.assertContains(response, "No accounts found")
        self.act(reason="Already handled")
        response = self.client.get(reverse("user_admin_list"), {"status": "suspended"})
        self.assertContains(response, "target@example.com")
        response = self.client.get(reverse("user_admin_list"), {"status": "active"})
        self.assertNotContains(response, "target@example.com")

    def test_detail_shows_audit_history(self):
        self.act(reason="Spam listings")
        page = self.client.get(self.detail_url())
        self.assertContains(page, "Spam listings")
        self.assertContains(page, "admin@example.com")
        self.assertContains(page, "Suspended")

    # --- suspend ---
    def test_suspend_blocks_login_and_is_audited(self):
        response = self.act(reason="Abusive behaviour")
        self.assertRedirects(response, self.detail_url())
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertIsNotNone(self.target.suspended_at)
        self.assertTrue(self.target.is_suspended)
        entry = AccountAction.objects.get()
        self.assertEqual((entry.target, entry.admin, entry.action, entry.reason), (self.target, self.admin, "suspend", "Abusive behaviour"))
        self.assertIsNotNone(entry.created_at)
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "target@example.com", "password": "Reading2026!"})
        self.assertContains(response, "Invalid credentials. Please try again.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_suspending_an_already_suspended_account_is_a_noop(self):
        self.act()
        response = self.act()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account is already suspended.")
        self.assertEqual(AccountAction.objects.count(), 1)

    def test_suspend_hides_the_sellers_listings(self):
        book = self.make_book()
        self.act()
        self.client.force_login(self.buyer)
        self.assertNotContains(self.client.get(reverse("catalog")), "Clean Code")
        self.assertEqual(self.client.get(reverse("book_detail", args=[book.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("cart_add", args=[book.pk])).status_code, 404)

    def test_an_existing_session_is_invalidated_after_suspension(self):
        target_client = Client()
        target_client.force_login(self.target)
        self.assertEqual(target_client.get(reverse("profile")).status_code, 200)
        self.act()
        response = target_client.get(reverse("profile"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('profile')}")

    # --- remove ---
    def test_remove_blocks_login_and_is_audited(self):
        response = self.act(action="remove", reason="Fraud")
        self.assertRedirects(response, self.detail_url())
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(self.target.is_removed)
        self.assertIsNotNone(self.target.removed_at)
        entry = AccountAction.objects.get()
        self.assertEqual((entry.action, entry.reason), ("remove", "Fraud"))
        self.client.logout()
        self.client.post(reverse("login"), {"username": "target@example.com", "password": "Reading2026!"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_removal_keeps_order_and_listing_history(self):
        book = self.make_book()
        order = Order.objects.create(user=self.target, total=Decimal("500"), shipping_address="12 Main Road")
        OrderItem.objects.create(order=order, book=book, quantity=1, unit_price=Decimal("500"))
        self.act(action="remove", reason="Fraud")
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(order.items.get().book, book)
        self.assertEqual(Book.objects.get(pk=book.pk).seller, self.target)

    def test_removed_account_cannot_be_acted_on_again(self):
        self.act(action="remove", reason="Fraud")
        response = self.act(action="suspend", reason="Again")
        self.assertContains(response, "Account is already removed.")
        self.assertEqual(AccountAction.objects.count(), 1)

    # --- guards ---
    def test_admin_cannot_suspend_or_remove_their_own_account(self):
        for action in ("suspend", "remove"):
            with self.subTest(action=action):
                response = self.act(action=action, reason="Mistake", user=self.admin)
                self.assertContains(response, "cannot suspend or remove your own account")
                self.admin.refresh_from_db()
                self.assertTrue(self.admin.is_active)
        self.assertFalse(AccountAction.objects.exists())

    def test_only_a_superuser_can_moderate_another_superuser(self):
        root = User.objects.create_superuser("root@example.com", "pw")
        response = self.act(action="suspend", reason="Test", user=root)
        self.assertContains(response, "Only a superuser can moderate another superuser")
        root.refresh_from_db()
        self.assertTrue(root.is_active)
        self.assertFalse(AccountAction.objects.exists())

    def test_reason_is_required(self):
        response = self.act(reason="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(AccountAction.objects.exists())

    def test_action_needs_post_and_csrf(self):
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        self.assertEqual(
            strict.post(self.detail_url(), {"action": "suspend", "reason": "No token"}).status_code, 403
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(AccountAction.objects.exists())

    def test_audit_records_have_no_application_write_permissions(self):
        self.assertEqual(AccountAction._meta.default_permissions, ("view",))
