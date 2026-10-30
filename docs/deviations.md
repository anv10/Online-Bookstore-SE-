# Deviations from the SRS, SAD and Test Plan

Where the build differs from the documents we submitted, and why. Status is as of 29 Oct 2026. Rows marked (check) depend on a pull request or issue that was still open when this was written, so update them before the final demo.

Sources: the SRS, Test Plan and architecture diagram in `Documents/`, the issues, and the notes in `docs/sprint2/`.

## Process and design

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-7 | 2-week sprints | 1-week sprints. The Sprint 1 video was due 23 Oct and the Sprint 2 video is due 30 Oct (issues #31, #32). | The course guide sets the demo dates a week apart. |
| NFR-7 | Code review before merge | PR #37 (the Django setup) was merged by its author with no approval. Branch protection (1 approval needed) was switched on on 20 Oct, so every PR after that needs a review. | The rule did not exist yet. It was set up as part of issue #22. |
| SAD | Architecture diagram | The diagram was drawn before we picked a framework. We use Django with PostgreSQL (decided in issue #21). The README is the current reference. | The framework was chosen after the diagram. |
| Test Plan | Test results columns | They still say Pending. Test evidence is in each `docs/sprint2/*.md` file (tests mapped to test IDs) and in CI. | Updating the plan is part of issue #33. |

## Functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| FR-1 (FR-1_UT03) | Registration rejects a blank phone number | Users register with an email or a phone number. Phone is not mandatory. | Issue #1 says email or phone. |
| FR-5 | Pay through an integrated gateway | Checkout uses a sandbox gateway with test cards (4242... works, 4000...0002 is declined). The payment reference is not stored on the order. Hosted payment with Stripe is in PR #73 (check). | The real gateway needs an account and a key. It was split into issue #10. |
| FR-6 | Confirmation email when an order is placed | Email only. Phone-only accounts get none. If sending fails it is logged and retried by `manage.py retry_order_confirmations`, which has to be run from cron. | There is no SMS service. |
| FR-8, FR-9 | Sellers manage orders, buyers track them | An order has one status. If it has books from several sellers, one seller cannot mark it shipped or delivered. | A status per item needs a new column and a migration. We left it out because the freeze was close. |
| FR-9 | Status: placed, shipped, out for delivery, delivered | The seller changes the status with buttons. There is no courier or shipping updates. "Out for delivery" is in PR #74 (check). | See NFR-11. |
| FR-10 (FR-10_UT02) | Review text is mandatory | Review text is optional. | Issue #18 says optional. |
| FR-11 | Discount codes at checkout | Not built. Issue #13 is still open and there is no coupon code in the repo. | Not finished in time. |
| FR-12 | Admins approve, suspend or remove listings | Done with a reason and an audit record for every decision. There is no flagged or reported workflow, and "reject" is done as suspend or remove. The seller sees the result on their listings page, not by email (UC16). | Issue #19 only asked for approve, suspend and remove. |
| FR-12 | Admins suspend or remove user accounts | "Remove" keeps the row and only blocks the account, so orders and reviews still point at a user. There is no restore. | Deleting the row would break order and review links. |
| FR-13 | Invoice after payment | The invoice is an HTML page that can be downloaded as an HTML file, not a PDF. Orders store item prices and one total, so discounts and taxes are worked out from the total. | No PDF library was added and orders have no separate tax or discount fields. |
| FR-14 | Reset a password by email or OTP | A reset link by email, valid one hour, single use. Accounts with only a phone number get nothing. There is no rate limit on the request page. | There is no SMS service. |

## Non-functional requirements

| Ref | What the documents say | What we did | Why |
| --- | --- | --- | --- |
| NFR-6 | Sensitive data encrypted in transit and at rest | Passwords use Argon2. Only the shipping address is encrypted in the database (email and phone are not). HTTPS settings are switched on with `DJANGO_FORCE_HTTPS=1`, but TLS itself is set up on the web server, and the site is not deployed yet. | Scope of issue #23. There is no server to configure. |
| NFR-11 | Payment and shipping use standard third-party APIs | Payment: see FR-5. Shipping: no shipping API (issue #24 is open). Shipping is a flat charge at checkout. | Stretch goal, not built. |
| NFR-12 | Support by chat or email, answered within 24 hours | Email only, shown in the footer. The 24 hours is a stated target, nobody measures it. | NFR-12 allows chat or email. |
| NFR-2 | 99.5% uptime, monitored | No health check and no monitor (issue #28 is open). | The site is not deployed. (check) |
| NFR-1, NFR-3 | 500 users under 2 seconds, scale out | No load test yet (issue #25 is open). Sessions are in the database, so servers are stateless, but uploaded book images are saved on the local disk, so more than one server would need shared storage. | Not done yet. (check) |
| NFR-4 | A first-time user buys within 5 minutes | Usability test not done yet (issue #29 is open). | Needs real people. (check) |
| NFR-5 | Works in Chrome, Firefox, Safari, Edge and on mobile | No cross-browser check recorded yet (issue #26 is open). The pages use one shared stylesheet with mobile rules. | Not done yet. (check) |
| NFR-10 | Privacy policy and data protection | No privacy policy page and no way to request account deletion (issue #27 is open). | Not built yet. (check) |

## To check with the team before the demo
- Whether PR #73 (Stripe) and PR #74 (out for delivery) are merged. If yes, change the FR-5 and FR-9 rows.
- Whether issues #24, #25, #26, #27, #28 and #29 get done before the freeze. Delete a row if its issue is finished, and keep the row if it is not.
- Whether the NFR-7 review row is worded the way the team wants.
