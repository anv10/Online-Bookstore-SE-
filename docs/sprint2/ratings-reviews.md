# Ratings and reviews: issue #18

Implements FR-10 on top of the existing Django/PostgreSQL application. Read alongside `Documents/SRS_Online_Bookstore.docx`, `Documents/TestPlan_Online_Bookstore.docx`, `Documents/SecurityRequirements_Online_Bookstore.docx` and `docs/sprint2/checkout-and-payment.md`.

## Buyer experience

1. A buyer sees the review form link on a book's details page only when an order containing that book has reached the **delivered** state. Pending, paid and shipped orders do not qualify.
2. The review form accepts a rating from 1 to 5 and optional review text (maximum 2000 characters). The rating is required; text is not.
3. One review is allowed per buyer per book. Opening the form again edits the same row rather than creating a duplicate.
4. The details page recalculates the average rating and review count on every request, so a new, edited or removed review is reflected immediately. Reviews show the reviewer's display name, never their email or phone number.
5. Anonymous visitors are sent to login. A buyer without a delivered purchase is redirected to the book page with "You must purchase this book to review it."

## Delivered orders

Review eligibility needs a delivered order, while the seller order screen previously stopped at **shipped**. This change adds the `delivered` order state and a "Mark as delivered" action for the seller who owns every item in a shipped order. This is the minimum needed to make FR-10 usable end to end; the complete buyer-facing tracking timeline (placed, shipped, out for delivery, delivered) remains issue #14.

## Admin removal

`reviews.Review` is registered in the Django admin with search and filters. An administrator with the `reviews.delete_review` permission can delete an inappropriate review; because the average is computed from the remaining rows, no separate recalculation job is needed. Deletion is audited by the normal Django admin log.

## Validation and test-plan mapping

Verified locally with the repository test suite. Run the PostgreSQL CI job before merge; local runs used an in-memory SQLite override because this machine has no PostgreSQL server.

| Submitted test ID | Evidence in `reviews/tests/test_reviews.py` / `orders/tests/test_seller_orders.py` | Limit |
| --- | --- | --- |
| FR-10_UT01 | `test_rating_outside_one_to_five_is_rejected` | Rating 0, 6, blank and non-numeric are rejected |
| FR-10_UT02 | `test_review_text_is_optional` | The issue makes text optional, so a blank review is accepted. This is a documented deviation from the test plan's mandatory-text expectation |
| FR-10_UT03 | `test_average_rating_updates_on_the_detail_page` | Average of 4, 5, 3 is 4.0 |
| FR-10_IT01 | `test_only_a_delivered_purchase_can_be_reviewed`, `test_someone_elses_delivered_order_does_not_count` | Delivered is stricter than the test plan's "purchased" wording |
| FR-10_IT02 | `test_average_rating_updates_on_the_detail_page` | Detail page shows the recalculated average |
| FR-10_IT03 | `test_review_is_editable_and_stays_a_single_row` and the model's unique constraint | A second submission edits the existing review; the database constraint blocks duplicates |
| FR-10_ST01 | `test_review_is_visible_to_other_buyers` | Another logged-in buyer sees the review and average |
| FR-10_ST02 | `test_admin_removal_recalculates_the_average` | Django admin deletion recomputes the average |

Additional coverage: hidden/pending listings (404), unknown books (404), login redirects, CSRF, escaped HTML, the seller delivery transition and its authorization checks.

## Deviations and remaining checks

- Review text is optional per issue #18, not mandatory as written in FR-10_UT02.
- Eligibility is "delivered", not merely "paid", per the issue acceptance criteria.
- Only the seller of every item in an order can mark that order delivered. Shared orders keep their existing restriction and will be handled with order tracking (#14).
- Browser, mobile, PostgreSQL locking and TLS/deployment checks remain part of the Sprint 2 validation and review process.
- AI-assisted implementation. Assigned team member submission, human review and approval remain separate steps.
