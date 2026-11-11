# Deviations from the SRS, SAD and Test Plan

Where the build differs from the documents we submitted, and why. Status is current as of the end of Sprint 2, after the 30 Oct freeze. Every issue and pull request referenced here is closed and merged.

The executed Test Plan, case by case with evidence, is in [`docs/testing/test-plan-results.md`](testing/test-plan-results.md). Of its 120 cases, 109 pass, 9 fail and 2 could not be run here; the failures are all explained by a row below.

Sources: the SRS, Test Plan and architecture diagram in `Documents/`, the issues, and the notes in `docs/sprint2/`.

## Process and design

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-7 | 2-week sprints | 1-week sprints. The Sprint 1 video was due 23 Oct and the Sprint 2 video was due 30 Oct (issues #31, #32). | The course guide sets the demo dates a week apart. |
| NFR-7 | Code review before merge | Branch protection requires one approving review from someone other than the author. Five of the eight post-freeze PRs (#80-#84) were merged through an administrator override because their author could not approve them and no other reviewer was available in time. Those five have no independent review on record. | Stated plainly rather than claimed as compliance. |
| SAD | Architecture diagram | The diagram was drawn before we picked a framework. We use Django with PostgreSQL (decided in issue #21). The README is the current reference. | The framework was chosen after the diagram. |
| Test Plan | Test results columns | The PDF still shows Pending in its own columns. The real results live in `docs/testing/test-plan-results.md`, which records all 120 cases with a result and a named test or code path per case. | The PDF is a submitted artefact; the results file is what actually gets kept up to date. |
| Test Plan | Two cases assume tooling we do not have | FR-2_ST02 (500 users in 2 seconds) and FR-15_ST02 (mobile/cross-browser) were not executed. | No load-test or device lab is set up; see NFR-1/NFR-3 and NFR-5 below. |

## Functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| FR-1 (FR-1_UT03) | Registration rejects a blank phone number | Users register with an email or a phone number. Phone is not mandatory. | Issue #1 says email or phone. |
| FR-1 (FR-1_ST02) | Warn or lock the account after repeated failed logins | Built: a temporary lockout after three failures, keyed on the identifier and expiring on its own. Every identifier, known or not, locks the same way. | Post-freeze work from PR #78. |
| FR-5 | Pay through an integrated gateway | Hosted Stripe Checkout (PR #73). The sandbox card 4242... succeeds, 4000...0002 is declined. Card data never reaches our database or logs. | The real gateway needs an account and a key; issue #10 supplied the Stripe integration. |
| FR-5 (FR-5_IT02) | A declined payment saves the order with status "Payment Failed" | No order row is created on a decline; the cart is kept so the buyer can retry. Payment attempts are recorded in the `Payment` table with status `failed`. | Writing an unpaid order row would let abandoned carts look like orders and would need a cleanup job. |
| FR-6 | Confirmation email when an order is placed | Email and SMS. SMS goes through a gateway seam (console for development, HTTP for a real provider) and is best effort: a carrier failure is logged and retried, never blocking the order. The text reads `order #12`, not the `ORD10234` form the Test Plan prints. | Post-freeze work from PR #79. The plan's sample ID format was never adopted in the application. |
| FR-6 (FR-6_UT03) | SMS shows the order ID as `ORD10234` | The ID is `order #<pk>`. | Order numbers are the database primary key everywhere else; inventing a second format for SMS was not worth the inconsistency. |
| FR-7 (FR-7_IT01, FR-7_ST01) | A new seller listing is searchable straight away | A new listing is saved as `pending` and stays out of search and the catalogue until an admin approves it. The seller sees the status on their listings page. | Issue #19 introduced the approval gate; it stops an unvetted seller from publishing directly. |
| FR-8, FR-9 | Sellers manage orders, buyers track them | An order still has one status. If it has books from several sellers, one seller cannot mark it shipped or delivered without affecting the others. | A status per item needs a new column and a migration. We left it out because the freeze was close. |
| FR-8 (FR-8_ST02) | Bulk status update | Built: checkboxes on the seller's order list ship several paid orders in one action. The batch is all-or-nothing, and an order shared with another seller blocks the batch. | Post-freeze work from PR #81. |
| FR-9 | Status: placed, shipped, out for delivery, delivered | Built with a status log, a seller-driven transition guard, and a carrier seam (`orders/logistics.py`): sandbox by default, `SHIPPING_PROVIDER=http` plus `SHIPPING_API_URL` for a documented carrier REST API. A carrier outage never blocks shipping. | Post-freeze work from PR #84. |
| FR-9 (FR-9_UT03) | Estimated delivery date | Ship date plus a transit estimate (5 days by default). Delivered orders show none. | Post-freeze work from PR #84. |
| FR-9 (FR-9_IT02) | Logistics webhook updates the order | `POST` endpoint with a shared-secret signature check; an unknown reference is a 404 and an unknown status is rejected. Disabled when no secret is configured. | Post-freeze work from PR #84. |
| FR-10 (FR-10_UT02) | Review text is mandatory | Required; an empty box is refused with "Review text is required." | Post-freeze work from PR #80. |
| FR-10 (FR-10_IT03) | A second review is rejected with "You have already reviewed this item" | A second submission edits the buyer's existing review and says "Your review was updated". The error only appears if two submissions race and hit the unique constraint. | Editing is better than an error for a buyer who wants to fix a typo; the constraint still guarantees one row per buyer per book. |
| FR-11 | Discount codes at checkout | Built: percentage or fixed-amount coupons, optional expiry, optional usage cap, optional minimum order value, one use counted per paid order. | Issues #13 and the follow-up minimum-order work in PR #82. |
| FR-11 (FR-11_ST02) | A second coupon is rejected | A second coupon replaces the first; the session holds one code at a time. | The checkout total has a single discount column, so stacking was never modelled. |
| FR-12 | Admins approve, suspend or remove listings | Done with a reason and an audit record for every decision. There is no flagged or reported workflow, and "reject" is done as suspend or remove. The seller sees the result on their listings page, not by email (UC16). | Issue #19 only asked for approve, suspend and remove. |
| FR-12 (FR-12_ST01) | A buyer flags a listing and an admin rejects it | No flag or report path exists. Moderation starts from the pending queue, not from a complaint. | Not in any Sprint 1 or Sprint 2 issue; the post-freeze PRs did not add it. |
| FR-12 | Admins suspend or remove user accounts | "Remove" keeps the row and only blocks the account, so orders and reviews still point at a user. There is no restore. | Deleting the row would break order and review links. |
| FR-13 | Invoice after payment | The invoice is an HTML page that can be downloaded as an HTML file, not a PDF. It is itemised per seller and shows the net amount after partial refunds. | No PDF library was added; per-seller itemisation and refunds came in PR #83. |
| FR-14 (FR-14_UT02) | Reset a password by OTP | A reset link by email, valid one hour, single use. There is no OTP entry screen. | No SMS provider was wired for account security, and a link is the safer default. |

## Non-functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-6 | Sensitive data encrypted in transit and at rest | Passwords use Argon2. Only the shipping address is encrypted in the database (email and phone are not). HTTPS settings are switched on with `DJANGO_FORCE_HTTPS=1`, but TLS itself is set up on the web server, and the site is not deployed yet. | Scope of issue #23. There is no server to configure. |
| NFR-11 | Payment and shipping use standard third-party APIs | Payment: Stripe, done. Shipping: a carrier seam with a sandbox default and an HTTP client for a documented carrier API, plus inbound status webhooks. No live carrier account was connected. | Issue #24 was closed as won't-do for a live account; the integration seam was built afterwards in PR #84. |
| NFR-12 | Support by chat or email, answered within 24 hours | Email only, shown in the footer. The 24 hours is a stated target, nobody measures it. | NFR-12 allows chat or email. |
| NFR-2 | 99.5% uptime, monitored | Not built. There is no health-check endpoint, no external monitor and no uptime report. Issue #28 was closed with its acceptance criteria still unticked. | The site is not deployed, so there is nothing to watch. |
| NFR-1, NFR-3 | 500 users under 2 seconds, scale out | Not measured. There is no load-test script in the repo. Sessions are in the database, so app servers are stateless, but uploaded book images are saved on the local disk, so a second server would need shared storage. Issue #25 was closed with its acceptance criteria still unticked. | No load-test environment. The session and media design is the part we can argue for. |
| NFR-4 | A first-time user buys within 5 minutes | Not tested with real users. Issue #29 was closed with its acceptance criteria still unticked. | Needs people outside the team. |
| NFR-5 | Works in Chrome, Firefox, Safari, Edge and on mobile | Not verified. The pages use one shared stylesheet with mobile rules, and no cross-browser or device run is recorded. Issue #26 was closed. | No device lab, and the two passing NFR-5 checks are the ones the Test Plan covers by hand. |
| NFR-10 | Privacy policy and data protection | Not built. There is no privacy policy page and no self-service account deletion. Issue #27 was closed. | Out of Sprint 1 and Sprint 2 scope; the admin moderation screen can remove an account on request. |

## Load-bearing gaps

If an examiner asks what is missing, these are the ones to volunteer. None of them is hidden in the code; each is a decision we made or a task we did not reach.

- **No independent review on five PRs.** #80-#84 were merged by administrator override; their author could not approve them. This is the most exposed row in the document because the course checklist asks for non-author review.
- The four NFR issues closed without the work being done (NFR-1, NFR-2, NFR-3, NFR-4) still say `COMPLETED` with their acceptance criteria unticked.
- Still absent from the product: a flag/report path for listings (FR-12_ST01), OTP password reset (FR-14_UT02), coupon stacking rejection (FR-11_ST02), phone as a required registration field (FR-1_UT03), an order row for a declined payment (FR-5_IT02), and immediate visibility of an unapproved listing (FR-7_IT01, FR-7_ST01).
- The Test Plan PDF still says Pending. `docs/testing/test-plan-results.md` is the honest record and should be shown instead.
