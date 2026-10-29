# Checkout and payment: issue #9

Implements FR-5 (checkout and place order) on the Django/PostgreSQL application. Read alongside `Documents/SRS_Online_Bookstore.docx` and `Documents/TestPlan_Online_Bookstore.docx` (FR-5 cases). Payment gateway ownership sits with issue #10; this change supplies the checkout flow and the gateway seam it plugs into.

## Flow

1. A signed-in buyer with items in the cart opens `/checkout/` from the cart page.
2. The page shows every line (book, copies, line total), then subtotal, tax, shipping and the grand total, with a shipping address box.

   The address is prefilled from the buyer's most recent order, so a repeat buyer can accept it or type a new one.
3. Address and card are validated on the server before any gateway call: the address must not be blank, the card must be 13-19 digits with a valid Luhn check digit, the expiry must be `MM/YY` and not in the past, and the security code must be 3-4 digits.
4. Checkout runs in one database transaction: the cart's books are row-locked and re-checked for approval, an active seller and enough stock; the card is charged; the order is created with status **Paid**; each `OrderItem` stores the unit price at purchase time; stock is decremented; and the cart is emptied.

   If the gateway declines the card, nothing is written: no order, no stock change and the cart stays intact so the buyer can retry.
5. The confirmation page shows the order id, books, copies, total paid, status and shipping address. It is reachable only by the buyer who owns the order; anyone else gets a 404.

An empty cart redirects back to the cart with a message. So does a cart holding an item that is suspended, removed, has an inactive seller or now has fewer copies than the cart requests. Availability and quantity are re-checked inside the transaction, so a copy cannot be oversold.

## Totals

`total = subtotal + tax + shipping`, rounded to 2 decimals with `ROUND_HALF_UP`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `CHECKOUT_TAX_RATE` | `0.05` | Tax applied to the subtotal |
| `CHECKOUT_SHIPPING_FLAT` | `50.00` | Flat shipping charge per order |

Example from the test plan: subtotal 500, tax 25, shipping 50, total 575.

## Payment gateway

`PAYMENT_GATEWAY=sandbox` selects the development/test provider in `orders/payments.py`. The sandbox behaves like a hosted gateway: it accepts or declines and returns a reference, and it never receives card data over the network.

| Card | Result |
| --- | --- |
| `4242 4242 4242 4242` | Accepted |
| `4000 0000 0000 0002` | Declined |

Any future expiry (`12/34`) and any 3-digit security code work with the sandbox. Card number, expiry and security code are never persisted, logged or put in the session, and the card inputs are rendered empty after a failed submission (NFR-6).

Issue #10 replaces the provider by implementing `charge()` against the chosen gateway SDK and switching `PAYMENT_GATEWAY`; the checkout view, totals and order transaction do not change.

## Concurrency

`Book.objects.select_for_update()` locks the rows for the checkout transaction, and each decrement uses a guarded `filter(stock__gte=quantity).update(...)` as a second line of defence. Two buyers racing for the last copy therefore produce one order; the other is told the copy sold out.

## Validation and test plan mapping

Local validation: Python 3.12.10, Django 5.2.18, in-memory SQLite override used only by the validation process (no local PostgreSQL is provisioned here). The full suite passes (169 tests) with 99% statement coverage, above the configured 70% gate; `manage.py check` and `makemigrations --check` are clean, and the repository PostgreSQL workflow passes on the pull request. SQLite cannot exercise PostgreSQL row locks or true concurrent transactions, so the concurrency case is covered by a deterministic last-copy test plus the guarded update in CI.

| Submitted test ID | Evidence in `orders/tests/test_checkout.py` | Note |
| --- | --- | --- |
| FR-5_UT01 | `test_address_is_required`, `test_whitespace_address_is_rejected` | Shows "Shipping address is required." |
| FR-5_UT02 | `test_invalid_card_number_is_rejected`, `test_invalid_expiry_is_rejected`, `test_invalid_security_code_is_rejected` | Shows "Invalid card number." for `1234` and a bad check digit |
| FR-5_UT03 | `test_total_is_subtotal_plus_tax_and_shipping` | 500 + 25 + 50 = 575, stored on the order |
| FR-5_IT01 | `test_successful_payment_creates_a_paid_order_and_clears_the_cart` | Order status `Paid` in the database |
| FR-5_IT02 | `test_declined_card_creates_no_order_and_keeps_the_cart` | No order, no stock change, cart retained |
| FR-5_IT03 | `test_stock_is_decremented_after_payment` | 10 in stock, buy 1, stock is 9 |
| FR-5_ST01 | `test_confirmation_page_shows_order_id_and_total` | Confirmation shows order id, total, address |
| FR-5_ST02 | `test_second_buyer_of_the_last_copy_is_told_it_sold_out` | Second buyer gets no order and a stock message |

Additional coverage: login and CSRF requirements, confirmation privacy, card values not echoed or stored, order-line price snapshot, unavailable/suspended listings, empty cart, and a misconfigured gateway reporting an error instead of crashing.

The submitted test plan statuses remain Pending; this addendum reports automated local evidence, not browser or PostgreSQL sign-off.

## Deviations and remaining checks

- The payment provider is the in-repo sandbox, not a hosted gateway. Issue #10 owns the hosted integration and its credentials; the acceptance criteria for #9 (order only after successful payment, no stored card data) hold with the sandbox.
- The payment reference returned by the gateway is not stored, because `Order` has no such column and adding one now would collide with the pending encrypted-address migrations in #23. When #10 lands the hosted gateway, add `payment_reference` with a migration.
- The confirmation page does not link to the invoice; issue #11 adds invoice generation. Order status tracking (#14) and the confirmation email (#12) are separate issues.
- Tax is one flat rate rather than per-region, and shipping is a flat charge rather than carrier-calculated; the test plan's expected numbers are met.
- The buyer enters a shipping address (prefilled from the last order); there is no saved-address book.
- Chrome/Firefox/Safari/Edge and mobile checks, PostgreSQL migration and row-lock behaviour, and deployment TLS remain unverified. Run the PostgreSQL CI workflow and manual browser checks before merge.
