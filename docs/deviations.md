# Deviations from the SRS, SAD and Test Plan

Where the build differs from the documents we submitted, and why. Status is current as of the end of Sprint 2. Every issue and pull request referenced here is closed and merged.

The executed Test Plan, case by case with evidence, is in [`docs/testing/test-plan-results.md`](testing/test-plan-results.md). All 120 cases now meet their stated Expected Result. The two cases that need more than the unit suite were run with dedicated tools: FR-2_ST02 with `manage.py load_test_search` and FR-15_ST02 in headless Chrome at a 390x844 viewport.

Sources: the SRS, Test Plan and architecture diagram in `Documents/`, the issues, and the notes in `docs/sprint2/`.

## Process and design

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| SAD | Architecture diagram | The diagram was drawn before we picked a framework. We use Django with PostgreSQL (decided in issue #21). The README is the current reference. | The framework was chosen after the diagram. |

## Functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| FR-1 (FR-1_UT03, FR-1_IT01) | Registration collects an email and a mandatory phone number | Registration has separate email and phone fields and both are required; a blank phone shows "Phone number is required". Login still accepts either email or phone. | The Test Plan treats the phone as a mandatory registration field, so the earlier email-or-phone form was replaced. |
| FR-1 (FR-1_ST02) | Warn or lock the account after repeated failed logins | Built: a temporary lockout after three failures, keyed on the identifier and expiring on its own. Every identifier, known or not, locks the same way. | The Test Plan's lockout case needed a concrete warning-and-lock behaviour. |
| FR-5 | Pay through an integrated gateway | Hosted Stripe Checkout (PR #73). The sandbox card 4242... succeeds, 4000...0002 is declined. Card data never reaches our database or logs. | The real gateway needs an account and a key; issue #10 supplied the Stripe integration. |
| FR-5 (FR-5_IT02) | A declined payment leaves the order unpaid and the cart intact | A declined card writes an order with status **Payment Failed** and its attempted line items, sends no confirmation, leaves stock untouched and keeps the cart for a retry. | The Test Plan asks for the failed order to be visible, so the row is written outside the rolled-back payment transaction. |
| FR-6 | Confirmation email when an order is placed | Email and SMS. SMS goes through a gateway seam (console for development, HTTP for a real provider) and is best effort: a carrier failure is logged and retried, never blocking the order. | The documents promise email only; the Test Plan's confirmation cases cover both channels. |
| FR-6 (FR-6_UT03) | SMS shows the order ID as `ORD10234` | The SMS now uses the `ORD` prefix over the zero-padded primary key, for example `ORD00012`. The rest of the site still prints `Order #12`. | The Test Plan fixes the carrier-facing format, so it was added without renaming the number the buyer sees everywhere else. |
| FR-7 (FR-7_IT01, FR-7_ST01) | A new seller listing is searchable straight away | A listing is published as approved as soon as the seller saves it, so it appears in search and the catalogue immediately. Moderators can suspend or remove it afterwards, and buyers can report it. | The Test Plan requires immediate visibility, so moderation is now report-driven and post-publication rather than a pre-publication gate. |
| FR-8, FR-9 | Sellers manage orders, buyers track them | An order still has one status. If it has books from several sellers, one seller cannot mark it shipped or delivered without affecting the others. | A status per item needs a new column and a migration. We left it out because the freeze was close. |
| FR-8 (FR-8_ST02) | Bulk status update | Built: checkboxes on the seller's order list ship several paid orders in one action. The batch is all-or-nothing, and an order shared with another seller blocks the batch. | The Test Plan has a bulk-update case, so the action was built for it. |
| FR-9 | Status: placed, shipped, out for delivery, delivered | Built with a status log, a seller-driven transition guard, and a carrier seam (`orders/logistics.py`): sandbox by default, `SHIPPING_PROVIDER=http` plus `SHIPPING_API_URL` for a documented carrier REST API. A carrier outage never blocks shipping. | The Test Plan tracks a shipped order end to end, so the full status pipeline was built for it. |
| FR-9 (FR-9_UT03) | Estimated delivery date | Ship date plus a transit estimate (5 days by default). Delivered orders show none. | The Test Plan asserts an estimated date on a shipped order. |
| FR-9 (FR-9_IT02) | Logistics webhook updates the order | `POST` endpoint with a shared-secret signature check; an unknown reference is a 404 and an unknown status is rejected. Disabled when no secret is configured. | The Test Plan drives the order through the carrier path. |
| FR-10 (FR-10_UT02) | Review text is mandatory | Required; an empty box is refused with "Review text is required." | The Test Plan refuses an empty review, so the field was made required. |
| FR-10 (FR-10_IT03) | A second review is rejected with "You have already reviewed this item" | A plain second submission is refused with that message and the first review is unchanged. The buyer can still edit deliberately through the "Edit your review" link, which carries `?edit=1`. | The plan forbids a silent second review; keeping an explicit edit path preserves the useful part of the old behaviour. |
| FR-11 | Discount codes at checkout | Built: percentage or fixed-amount coupons, optional expiry, optional usage cap, optional minimum order value, one use counted per paid order. | Issue #13 and the follow-up minimum-order work. |
| FR-11 (FR-11_ST02) | A second coupon is rejected | A second code is refused with "Only one coupon can be applied per order." and the first code stays applied. | The checkout total has a single discount column, so stacking was never modelled. |
| FR-12 | Admins approve, suspend or remove listings | Done with a reason and an audit record for every decision. Buyers can report a listing from its detail page; open reports get their own moderation queue tab and are settled when a moderator decides on the listing. Sellers see the result on their listings page, not by email (UC16). | Issue #19 asked for approve, suspend and remove; the report path now covers Test Plan FR-12_ST01. |
| FR-12 (FR-12_ST01) | A buyer flags a listing and an admin rejects it | Built: a signed-in buyer submits a reason, the listing appears under "Reported by buyers", and a reject/remove decision hides it from buyers and marks the report upheld. | Added to close the last missing moderation path. |
| FR-12 | Admins suspend or remove user accounts | "Remove" keeps the row and only blocks the account, so orders and reviews still point at a user. There is no restore. | Deleting the row would break order and review links. |
| FR-13 | Invoice after payment | The invoice is an HTML page that can be downloaded as an HTML file, not a PDF. It is itemised per seller and shows the net amount after partial refunds. | No PDF library was added. |
| FR-14 (FR-14_UT02) | Reset a password by OTP | Both paths exist: the emailed link (one hour, single use) and a six digit OTP emailed alongside it. The OTP expires after ten minutes, allows five attempts, is single use, and reports an expired code separately from a wrong one. | The Test Plan's OTP cases needed an entry screen; the link remains the safer default. |

## Non-functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-6 | Sensitive data encrypted in transit and at rest | Passwords use Argon2. Only the shipping address is encrypted in the database (email and phone are not). HTTPS settings are switched on with `DJANGO_FORCE_HTTPS=1`, but TLS itself is set up on the web server, and the site is not deployed yet. | Scope of issue #23. There is no server to configure. |
| NFR-11 | Payment and shipping use standard third-party APIs | Payment: Stripe, done. Shipping: a carrier seam with a sandbox default and an HTTP client for a documented carrier API, plus inbound status webhooks. No live carrier account was connected. | Issue #24 was closed as won't-do for a live account; the integration seam was built instead. |
| NFR-12 | Support by chat or email, answered within 24 hours | Email only, shown in the footer. The 24 hours is a stated target, nobody measures it. | NFR-12 allows chat or email. |
| NFR-2 | 99.5% uptime, monitored | Not built. There is no health-check endpoint, no external monitor and no uptime report. Issue #28 was closed with its acceptance criteria still unticked. | The site is not deployed, so there is nothing to watch. |
| NFR-1, NFR-3 | 500 users under 2 seconds, scale out | NFR-1 is measured locally by `manage.py load_test_search`: 500 searches over 50 workers returned p95 1.04 s against SQLite. Scale-out is still not deployed: sessions are in the database, but uploaded book images are on local disk. Issue #25 was closed with its acceptance criteria still unticked. | The latency target now has repeatable evidence; there is still no multi-server environment. |
| NFR-4 | A first-time user buys within 5 minutes | Not tested with real users. Issue #29 was closed with its acceptance criteria still unticked. | Needs people outside the team. |
| NFR-5 | Works in Chrome, Firefox, Safari, Edge and on mobile | The Test Plan's mobile case was checked in Chrome at 390x844, where the wishlist shows the same item as at 1366x900. Safari, Firefox and Edge were not run. Issue #26 was closed. | No device lab and no cross-browser run. |
| NFR-10 | Privacy policy and data protection | Not built. There is no privacy policy page and no self-service account deletion. Issue #27 was closed. | Out of Sprint 1 and Sprint 2 scope; the admin moderation screen can remove an account on request. |

## Load-bearing gaps

If an examiner asks what is missing, these are the ones to volunteer. None of them is hidden in the code; each is a decision we made or a task we did not reach.

- The four NFR issues closed without the work being done (NFR-1, NFR-2, NFR-3, NFR-4) still say `COMPLETED` with their acceptance criteria unticked. NFR-1 now has a local benchmark, but no deployed load test.
- Full Safari, Firefox and Edge verification, and usability testing with real first-time buyers, are still not done.
- The Test Plan PDF still says Pending. `docs/testing/test-plan-results.md` is the honest record and should be shown instead.
