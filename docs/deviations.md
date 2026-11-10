# Deviations from the SRS, SAD and Test Plan

Where the build differs from the documents we submitted, and why. Status is as of 10 Nov 2026, after the 30 Oct freeze. Every issue and pull request referenced here is closed and merged.

The executed Test Plan, case by case with evidence, is in [`docs/testing/test-plan-results.md`](testing/test-plan-results.md). Of its 120 cases, 97 pass, 21 fail and 2 could not be run here; the failures are all explained by a row below.

Sources: the SRS, Test Plan and architecture diagram in `Documents/`, the issues, and the notes in `docs/sprint2/`.

## Process and design

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-7 | 2-week sprints | 1-week sprints. The Sprint 1 video was due 23 Oct and the Sprint 2 video was due 30 Oct (issues #31, #32). | The course guide sets the demo dates a week apart. |
| NFR-7 | Code review before merge | PR #37 (the Django setup) was merged by its author with no approval. Branch protection (1 approval needed) was switched on on 20 Oct, so every PR after that has a non-author review; the Sprint 2 reviews are substantive, not rubber stamps. | The rule did not exist yet. It was set up as part of issue #22. |
| SAD | Architecture diagram | The diagram was drawn before we picked a framework. We use Django with PostgreSQL (decided in issue #21). The README is the current reference. | The framework was chosen after the diagram. |
| Test Plan | Test results columns | The PDF still shows Pending in its own columns. The real results live in `docs/testing/test-plan-results.md`, which records all 120 cases with a result and a named test or code path per case. | The PDF is a submitted artefact; the results file is what actually gets kept up to date. |
| Test Plan | Two cases assume tooling we do not have | FR-2_ST02 (500 users in 2 seconds) and FR-15_ST02 (mobile/cross-browser) were not executed. | No load-test or device lab is set up; see NFR-1/NFR-3 and NFR-5 below. |

## Functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| FR-1 (FR-1_UT03) | Registration rejects a blank phone number | Users register with an email or a phone number. Phone is not mandatory. | Issue #1 says email or phone. |
| FR-1 (FR-1_ST02) | Warn or lock the account after repeated failed logins | Not built. A wrong password only produces the same generic error as an unknown account. | Not in any Sprint 1 or Sprint 2 issue; there is no throttling library wired in. |
| FR-5 | Pay through an integrated gateway | Hosted Stripe Checkout (PR #73). The sandbox card 4242... succeeds, 4000...0002 is declined. Card data never reaches our database or logs. | The real gateway needs an account and a key; issue #10 supplied the Stripe integration. |
| FR-5 (FR-5_IT02) | A declined payment saves the order with status "Payment Failed" | No order row is created on a decline; the cart is kept so the buyer can retry. Payment attempts are recorded in the `Payment` table with status `failed`. | Writing an unpaid order row would let abandoned carts look like orders and would need a cleanup job. |
| FR-6 | Confirmation email when an order is placed | Email only. Phone-only accounts get none. If sending fails it is logged and retried by `manage.py retry_order_confirmations`, which has to be run from cron. No SMS. | There is no SMS service. |
| FR-7 (FR-7_IT01, FR-7_ST01) | A new seller listing is searchable straight away | A new listing is saved as `pending` and stays out of search and the catalogue until an admin approves it. The seller sees the status on their listings page. | Issue #19 introduced the approval gate; it stops an unvetted seller from publishing directly. |
| FR-8, FR-9 | Sellers manage orders, buyers track them | An order has one status. If it has books from several sellers, one seller cannot mark it shipped or delivered without affecting the others. | A status per item needs a new column and a migration. We left it out because the freeze was close. |
| FR-9 | Status: placed, shipped, out for delivery, delivered | The seller drives the status with buttons: placed, paid, shipped, out for delivery (PR #74), delivered, cancelled. Invalid jumps are rejected. There is no courier feed. | See NFR-11. |
| FR-9 (FR-9_UT03, FR-9_IT01, FR-9_IT02, FR-9_IT03) | Live courier status, an estimated delivery day, a webhook and a status-history timeline | None of it. The tracker is drawn from the current status, so it shows the steps reached but has no timestamps or provider data. | These all depend on the shipping API that was dropped with issue #24. |
| FR-10 (FR-10_UT02) | Review text is mandatory | Review text is optional; the rating is what is required. | Issue #18 says optional. |
| FR-10 (FR-10_IT03) | A second review is rejected with "You have already reviewed this item" | A second submission edits the buyer's existing review and says "Your review was updated". The error only appears if two submissions race and hit the unique constraint. | Editing is better than an error for a buyer who wants to fix a typo; the constraint still guarantees one row per buyer per book. |
| FR-11 | Discount codes at checkout | Built: percentage or fixed-amount coupons, optional expiry, optional usage cap, one use counted per paid order. There is no minimum-order-value field. | Issue #13 scoped codes, expiry and usage limits only. |
| FR-11 (FR-11_ST02) | A second coupon is rejected | A second coupon replaces the first; the session holds one code at a time. | The checkout total has a single discount column, so stacking was never modelled. |
| FR-12 | Admins approve, suspend or remove listings | Done with a reason and an audit record for every decision. There is no flagged or reported workflow, and "reject" is done as suspend or remove. The seller sees the result on their listings page, not by email (UC16). | Issue #19 only asked for approve, suspend and remove. |
| FR-12 | Admins suspend or remove user accounts | "Remove" keeps the row and only blocks the account, so orders and reviews still point at a user. There is no restore. | Deleting the row would break order and review links. |
| FR-13 | Invoice after payment | The invoice is an HTML page that can be downloaded as an HTML file, not a PDF. It lists every item flat: there is no per-seller split and no partial-refund adjustment. | No PDF library was added, orders carry one total, and there is no partial-refund feature to reflect. |
| FR-14 | Reset a password by email or OTP | A reset link by email, valid one hour, single use. Accounts with only a phone number get nothing, and there is no OTP entry screen. | There is no SMS service. |

## Non-functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-6 | Sensitive data encrypted in transit and at rest | Passwords use Argon2. Only the shipping address is encrypted in the database (email and phone are not). HTTPS settings are switched on with `DJANGO_FORCE_HTTPS=1`, but TLS itself is set up on the web server, and the site is not deployed yet. | Scope of issue #23. There is no server to configure. |
| NFR-11 | Payment and shipping use standard third-party APIs | Payment: Stripe, done. Shipping: no shipping API. Shipping is a flat charge at checkout. Issue #24 was closed as won't-do after the freeze. | Stretch goal. No carrier offers a sandbox we could reach in the time left. |
| NFR-12 | Support by chat or email, answered within 24 hours | Email only, shown in the footer. The 24 hours is a stated target, nobody measures it. | NFR-12 allows chat or email. |
| NFR-2 | 99.5% uptime, monitored | Not built. There is no health-check endpoint, no external monitor and no uptime report. Issue #28 was closed with its acceptance criteria still unticked. | The site is not deployed, so there is nothing to watch. |
| NFR-1, NFR-3 | 500 users under 2 seconds, scale out | Not measured. There is no load-test script in the repo. Sessions are in the database, so app servers are stateless, but uploaded book images are saved on the local disk, so a second server would need shared storage. Issue #25 was closed with its acceptance criteria still unticked. | No load-test environment. The session and media design is the part we can argue for. |
| NFR-4 | A first-time user buys within 5 minutes | Not tested with real users. Issue #29 was closed with its acceptance criteria still unticked. | Needs people outside the team. |
| NFR-5 | Works in Chrome, Firefox, Safari, Edge and on mobile | Not verified. The pages use one shared stylesheet with mobile rules, and no cross-browser or device run is recorded. Issue #26 was closed. | No device lab, and the two passing NFR-5 checks are the ones the Test Plan covers by hand. |
| NFR-10 | Privacy policy and data protection | Not built. There is no privacy policy page and no self-service account deletion. Issue #27 was closed. | Out of Sprint 1 and Sprint 2 scope; the admin moderation screen can remove an account on request. |

## Load-bearing gaps

If an examiner asks what is missing, these are the ones to volunteer. None of them is hidden in the code; each is a decision we made or a task we did not reach.

- Repeating the table above: no SMS, no OTP, no login lockout, no courier integration, no partial refund, no per-seller invoice split, no flag/report workflow, no bulk order update, no coupon minimum.
- The four NFR issues closed without the work being done (NFR-1, NFR-2, NFR-3, NFR-4) are the weakest part of the submission. The issues say `COMPLETED`, the acceptance criteria are unticked.
- The Test Plan PDF still says Pending. `docs/testing/test-plan-results.md` is the honest record and should be shown instead.
