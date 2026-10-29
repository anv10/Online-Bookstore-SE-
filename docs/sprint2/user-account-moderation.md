# Admin user account moderation: issue #20

Implements the account half of FR-12. Listing moderation is issue #19 and is documented separately in `docs/sprint2/admin-moderation.md`.

## Provisioning

Account administrators need an active account with `is_staff=True` and the `accounts.change_user` permission. Superusers qualify. Staff status alone, or the permission without staff status, is not enough. The "Users" link appears in the navigation only for accounts that hold the permission; every endpoint checks it again on the server.

## Workflow

1. Open **Users** in the navigation or `/accounts/admin/users/`.
2. Search by email, phone or full name and filter by Active, Suspended, Removed or All.
3. Open an account to see its status, join date and complete moderation history.
4. Choose **Suspended** or **Removed**, enter a reason and submit.

Suspending or removing an account sets `is_active=False`, so existing sessions stop authenticating on their next request and future logins fail with the same generic error as any other invalid credential. Suspending also hides every active listing owned by that seller from search, details pages and cart additions.

Removal is a soft delete: the user row, listings, orders and reviews stay because order history references them. Removed accounts cannot be acted on again. An administrator cannot moderate their own account, and only a superuser can moderate another superuser.

Every successful action creates one `AccountAction` row in the same transaction, recording the target, admin, action, reason and timestamp. The model has view permission only, has no application write endpoints, and is registered read-only in Django admin.

## Validation and test-plan mapping

Verified locally with the repository test suite. Run the PostgreSQL CI job before merge; local runs used an in-memory SQLite override because this machine has no PostgreSQL server.

| Submitted test ID | Evidence in `accounts/tests/test_user_moderation.py` | Limit |
| --- | --- | --- |
| FR-12_UT01 | `test_suspending_an_already_suspended_account_is_a_noop` | The UI reports "Account is already suspended" and writes no duplicate audit row |
| FR-12_IT01 | `test_suspend_hides_the_sellers_listings` | Search, details and cart-add all hide the suspended seller's approved book |
| FR-12_IT03 | `test_suspend_blocks_login_and_is_audited`, `test_remove_blocks_login_and_is_audited` | Audit row contains admin, target, action, reason and timestamp |
| FR-12_ST02 | `test_buyers_and_sellers_are_denied`, `test_staff_without_permission_and_permission_without_staff_are_denied` | Non-admins receive 403 on every account-moderation endpoint |

Additional coverage: search and status filters, the navigation link, login blocking, invalidation of an existing session, history retention for orders and listings, removal idempotency, self-protection, superuser protection, required reason, POST-only actions and CSRF.

## Deviations and remaining checks

- "Remove account" is a soft removal, not a database delete, so order and review foreign keys remain valid. There is no self-service or admin restore flow in this change.
- Account administrators are provisioned with Django staff plus the `accounts.change_user` permission, matching the existing listing-moderation approach.
- The custom account screens do not require the email second factor used by listing moderation (#19); both are staff- and permission-gated, but this change does not claim MFA for account moderation.
- Browser, mobile, PostgreSQL locking and TLS/deployment checks remain part of the Sprint 2 validation and review process.
- AI-assisted implementation. Assigned team member submission, human review and approval remain separate steps.
