# Security Validation Report

Validation of SEC-1 to SEC-39 from `Documents/SecurityRequirements_Online_Bookstore`. Version 1.0, 18-11-2026. The formatted copy is [`Documents/SecurityValidationReport_Online_Bookstore.docx`](../../Documents/SecurityValidationReport_Online_Bookstore.docx) (also as PDF).

**Result: 39 of 39 requirements pass** (4 also need a check once deployed). Before this work: 19 met, 12 partial, 8 missing. Security suite: 98 tests; full suite: 578 tests, all passing, 95% coverage. pip-audit and Bandit are clean.

Re-run with `python manage.py test security -v 2`. Raw output of every run is in [`security-evidence/`](security-evidence/).

## Gaps found and fixed

| Req | State before | What was missing |
| --- | --- | --- |
| SEC-5 | Partial | The emailed reset link stayed valid for one hour; section 4 proposes 10 minutes. |
| SEC-6 | Missing | Every reset request emailed a new link and code with no limit, so the feature could flood an inbox. |
| SEC-8 | Missing | Sessions lasted Django's default two weeks with no idle timeout. |
| SEC-14 | Partial | Only the listing moderation pages asked for the emailed code. User account moderation and the Django admin at /admin/ needed only the password. |
| SEC-17 | Partial | Only the shipping address was encrypted; phone numbers were stored in plain text. |
| SEC-18 | Partial | The reset token stayed in the address bar after the link was opened. Registration, OTP and checkout views did not mark their secrets as sensitive for error reports. |
| SEC-19 | Partial | DEBUG was off, but only a 404 page existed; 403, 400 and 500 fell back to Django's bare defaults. |
| SEC-20 | Missing | No backup procedure existed. |
| SEC-21 | Partial | No card data was stored, but the sandbox path also threw away the gateway's transaction reference. |
| SEC-23 | Partial | A gateway timeout escaped as an unhandled 500 error (no order was made, but the failure was not handled). A success with no reference was accepted. |
| SEC-24 | Partial | Coupons were validated on the server, but there was no per-buyer limit and no limit on guessing codes. |
| SEC-29 | Missing | There was no content filter; every review was published at once. |
| SEC-30 | Partial | Only the per-identifier login lockout existed; registration, reset and search had no limits, and one address could try many identifiers. |
| SEC-31 | Missing | There was no security event log; only a few unrelated warnings were logged. |
| SEC-32 | Partial | Moderation audit tables were read-only in admin, but there was no general security log, no protection at database level and no retention. |
| SEC-34 | Missing | No privacy notice existed (listed as a gap in docs/deviations.md). |
| SEC-35 | Missing | There was no self-service correction or deletion. |
| SEC-36 | Partial | The carrier client would call any SHIPPING_API_URL, including plain http:// or file:// (Bandit B310). |
| SEC-38 | Missing | No dependency scanning. pip-audit found 42 known vulnerabilities in Pillow 12.3.0 (requirements capped it below 13). |
| SEC-39 | Partial | Some rules had tests, but there was no security item in review and no static analysis. |

## Results by requirement

Test classes are in `security/tests/test_sec_requirements.py`.

| Req | Requirement | Implementation | Verification | Result |
| --- | --- | --- | --- | --- |
| **3.1 Authentication and account security** | | | | |
| SEC-1 | Passwords of 8+ characters with a letter and a digit, at registration, change and reset | RegistrationForm and SetNewPasswordForm run Django's validators (minimum length 8, common, numeric, similarity) plus a letter-and-digit rule (accounts/forms.py). | SEC01PasswordPolicyTests: four weak passwords refused at registration and at reset; a strong one accepted. | Pass |
| SEC-2 | Salted hashes with a slow adaptive algorithm; no plain or reversible passwords | Argon2id is the first entry in PASSWORD_HASHERS (bookstore/settings.py). | SEC02PasswordStorageTests: hash starts with argon2$argon2id$, two users with the same password get different hashes, and no row of accounts_user contains the password. | Pass |
| SEC-3 | Warning and temporary lock after 3 failed logins | LoginThrottle counts failures per typed identifier; the 3rd failure locks it for 15 minutes and shows the warning (accounts/throttle.py, accounts/forms.py). Lockouts are now also written to the security log. | SEC03LockoutTests: warning text after 3 failures, correct password refused while locked, lock lifts after 15 minutes, LOCKOUT event recorded. | Pass |
| SEC-4 | Generic login and reset messages that do not reveal accounts | One 'Invalid credentials' message; unknown identifiers lock the same way; reset always redirects to the same 'sent' page; the login backend hashes a dummy password for unknown accounts to equalise timing. | SEC04GenericMessagesTests: identical errors for known and unknown accounts, unknown identifiers lock, identical reset replies. | Pass |
| SEC-5 | Reset links and OTPs single use and short-lived | PASSWORD_RESET_TIMEOUT lowered to 600 s, so the link and the OTP both expire after 10 minutes. Both are single use (OTP used_at, token bound to the password hash). | SEC05ResetCodeLifetimeTests: OTP refused on second use and after expiry; link refused after 11 minutes and after use. | Pass |
| SEC-6 | Limit OTP and reset requests per account | At most 5 reset messages per account per hour (RATE_LIMITS['password_reset_account']); further requests send nothing but get the same reply (accounts/views.py, security/ratelimit.py). | SEC06ResetRequestLimitTests: six requests send five emails, all six get the same redirect, one RATE_LIMITED event. | Pass |
| **3.2 Session management** | | | | |
| SEC-7 | Random session token at login, sent only over TLS, cookie Secure and HttpOnly | Django issues a new random session key at login (session fixation protection). Cookie is HttpOnly and SameSite=Lax; DJANGO_FORCE_HTTPS=1 adds Secure. | SEC07SessionTokenTests: key changes at login, at least 32 characters, HttpOnly and SameSite set, Secure when HTTPS is enforced. | Pass |
| SEC-8 | Session expires after inactivity; logout invalidates it on the server | SESSION_COOKIE_AGE = 1800 with SESSION_SAVE_EVERY_REQUEST, so a session ends after 30 idle minutes; sessions also end when the browser closes. Logout deletes the session row. | SEC08SessionExpiryTests: idle session redirected to login; a copied session cookie stops working after logout. | Pass |
| SEC-9 | All sessions end when the password is changed or reset | Django's session auth hash includes the password hash, so every other session is invalid after a reset by link or by OTP. | SEC09SessionsEndOnPasswordChangeTests: a second device is logged out after both the OTP and the link reset. | Pass |
| **3.3 Access control and authorisation** | | | | |
| SEC-10 | Role-based access checked on the server for every request | login_required on every account view; seller views require catalog.add_book; moderation requires staff plus model permission. Denials raise PermissionDenied (403), which is now logged. | SEC10RoleBasedAccessTests: 10 protected URLs send anonymous users to login; a buyer typing 8 seller/admin URLs gets 403; /admin/ sends a buyer to the admin login. | Pass |
| SEC-11 | Buyers see only their own orders, cart and wishlist | Every lookup is filtered by the signed-in user; another buyer's record answers 404 and the attempt is logged as an authorisation failure. | SEC11BuyerDataIsolationTests: another buyer's order, invoice, download and confirmation are 404; their cart and wishlist items cannot be changed. | Pass |
| SEC-12 | Sellers manage only their own listings and orders | Listings are fetched by seller; seller order views only see orders that contain the seller's books. | SEC12SellerOwnershipTests: another seller's listing cannot be edited or removed; orders without the seller's books cannot be viewed, shipped or delivered. | Pass |
| SEC-13 | Only admins moderate; each action records who, what, why and when | AccountAction and ModerationEvent rows store admin, target, reason and time; both are read-only in Django admin. Each decision is also a security event. | SEC13AdminActionsTests: audit rows have all four fields; buyers and sellers get 403 and leave no audit rows. | Pass |
| SEC-14 | Second authentication step for admin accounts | One emailed 6-digit code (10 minutes, single use, hashed, bound to the session, 5 per hour) now unlocks every admin area for 30 minutes: AdminSecondFactorMiddleware guards /admin/, and the user and listing moderation views check it after their permission check (security/second_factor.py, security/middleware.py). | SEC14AdminSecondFactorTests: all three admin areas redirect to verification; a wrong code fails, the right one returns the admin to the page they asked for; next= cannot point off-site. | Pass |
| SEC-15 | Only buyers with a delivered order can review the book | has_delivered_purchase() is checked before a new review is accepted (reviews/views.py). | SEC15VerifiedPurchaseReviewTests: a shipped-but-not-delivered order is refused; a delivered one may review. | Pass |
| **3.4 Data protection** | | | | |
| SEC-16 | TLS 1.2+ for all traffic; HTTP redirected to HTTPS | DJANGO_FORCE_HTTPS=1 turns on SSL redirect, one-year HSTS with subdomains and Secure cookies. TLS 1.2+ is set on the web server or proxy in front of Django. | SEC16TransportSecurityTests: plain HTTP gets a 301 to https://, HTTPS responses carry HSTS. Existing HttpsSettingsTests cover the switch. | Pass (deployment check) |
| SEC-17 | Phone numbers and shipping addresses encrypted at rest | User.phone is now an encrypted column (Fernet). A keyed HMAC (phone_digest) handles login by phone and uniqueness. Migration accounts.0006 encrypts existing numbers and can be reversed. | SEC17EncryptionAtRestTests: raw column holds no digits, login by phone still works, duplicates are still refused, address is encrypted. Migration run forward and back on real data (section 7.6). | Pass |
| SEC-18 | No passwords, OTPs, tokens or card data in logs, URLs or error messages | The token is moved into the session and the URL rewritten to .../set-password/. sensitive_post_parameters on register, reset, OTP and checkout. Security events hold no secrets; failed-login identifiers are masked. | SEC18NoSecretsInLogsOrUrlsTests: after a failed login, reset, wrong OTP and a declined and an accepted payment, no password, code or card number appears in any log line, security event or page; the token is gone from the final URL. | Pass |
| SEC-19 | Generic error messages; details only in server logs | Generic 400, 403, 404, 429 and 500 templates. The 500 page has no template logic, so it renders even when the database is down. | SEC19GenericErrorPagesTests: an unhandled error mentioning a table name gives a generic 500 page, while the detail goes to the django.request log; 404 is generic; DEBUG is off. | Pass |
| SEC-20 | Encrypted backups, access limited to authorised staff | manage.py encrypted_backup runs pg_dump and writes it encrypted with BACKUP_ENCRYPTION_KEY (no fallback key) to a 0600 file in a 0700 directory; --decrypt restores it. | SEC20EncryptedBackupTests plus a real pg_dump run (section 7.5): refuses without a key, file is 0600 and contains no plain text, decrypts only with the right key. | Pass (deployment check) |
| **3.5 Payment security** | | | | |
| SEC-21 | No card data stored; only the transaction reference kept | Card fields are never saved, logged, put in the session or echoed back. New Order.payment_reference keeps the gateway reference (sandbox reference or Stripe payment intent). | SEC21NoCardStorageTests: after a checkout, every table is scanned as text for the card number and none contains it; the order has its reference; no card fields exist on Order or OrderItem. | Pass |
| SEC-22 | All amounts calculated on the server | Totals come from locked book rows, the server-side coupon and settings (orders/checkout.py); the browser sends only address and card. | SEC22ServerSideTotalsTests: tampered total, price, discount, tax and shipping fields are ignored; the order is 470.00 as calculated. | Pass |
| SEC-23 | Order created only after a verified gateway success; timeout or unknown result creates none | Gateway errors and successes without a reference raise PaymentUnconfirmed: no order, cart and stock untouched, a clear message, a PAYMENT_FAILED event. The Stripe return URL is checked with Stripe before an order exists. | SEC23VerifiedPaymentTests: timeout, reference-less success, declined card and a forged Stripe return all leave no paid order and an intact cart and stock. | Pass |
| SEC-24 | Coupons validated on the server, per-buyer limits, guessing rate limited | Coupon.max_uses_per_buyer, checked when the code is applied and again inside the order transaction. After 10 rejected codes in 15 minutes the buyer is paused; each rejection is logged. | SEC24CouponAbuseTests: a used-up code is refused for that buyer but works for another, the limit is rechecked at payment, the 11th attempt is blocked even for a valid code, the discount comes from the server. | Pass |
| **3.6 Input handling and application security** | | | | |
| SEC-25 | All input validated on the server for type, length and format | Django forms on every input: search length 255 and non-negative prices, email and phone formats, listing price and stock ranges, cart quantity range, integer URL converters. | SEC25InputValidationTests: over-long search, negative or non-numeric prices, bad email and phone, negative listing price and stock, and bad cart quantities are all refused. | Pass |
| SEC-26 | Parameterised queries; no SQL injection | Only the Django ORM is used in application code; raw SQL appears only in migrations and the backup command (fixed argv). | SEC26SqlInjectionTests: injection strings in search and login are treated as text and no table is dropped; a source scan finds no raw SQL in application code. Bandit: no findings (section 7.3). | Pass |
| SEC-27 | User content encoded on display (no XSS) | Django auto-escaping; no \|safe, mark_safe or autoescape off anywhere in the templates. | SEC27OutputEncodingTests: script and img payloads in listing titles, descriptions and reviews are escaped; a template scan finds no \|safe. | Pass |
| SEC-28 | CSRF protection on state-changing requests | CsrfViewMiddleware is on, and every form has a token. The one csrf_exempt endpoint (carrier webhook) requires an HMAC signature. CSRF failures are now logged. | SEC28CsrfTests: nine state-changing POSTs without a token get 403 and change nothing; an unsigned webhook gets 403. | Pass |
| SEC-29 | Reviews flagged by the content filter held until an admin approves | reviews/content_filter.py holds reviews with abusive words, spam phrases, links, markup or contact details. Held reviews are not shown or counted; admins approve or reject them with Django admin actions (logged). | SEC29ReviewModerationTests: three kinds of flagged text are held and hidden from the page and the rating; clean text publishes; an admin approval publishes a held review. | Pass |
| SEC-30 | Login, registration, reset and search rate limited | Per-address fixed-window limits kept in the database (shared by every app server): login 20 per 5 minutes, registration 10 per hour, reset 10 per hour, OTP entry 20 per hour, search 120 per minute. Over the limit: 429 page and a logged event. | SEC30RateLimitTests: each of the five entry points answers 429 one request past its limit, other addresses are unaffected, and counts live in the database. The 500-user load test still passes (section 7.4). | Pass |
| **3.7 Logging and monitoring** | | | | |
| SEC-31 | Log logins, lockouts, resets, admin actions, authorisation failures and failed payments, with time and user id | security.events.record() writes a SecurityEvent row (time, kind, user id, IP, path, short detail) and a line to the bookstore.security logger for 20 event kinds, including all those listed in SEC-31 plus CSRF, rate-limit, coupon and webhook rejections. | SEC31SecurityEventLogTests: failed and successful login, logout, lockout, reset request, authorisation failure and failed payment each produce an event with time, IP and user id; events also reach the logger. | Pass |
| SEC-32 | Logs protected from change, readable only by authorised staff, kept for a fixed period | SecurityEvent refuses updates and deletes in Python. A PostgreSQL trigger refuses UPDATE and any DELETE of rows younger than 90 days. The Django admin view is read-only and needs view permission. manage.py purge_security_events applies the 90-day retention. | SEC32ProtectedLogTests: edits and deletes are refused in Python and in raw SQL, admin offers no add, change or delete, and the purge removes only rows older than 90 days. Trigger also shown with psql (section 7.6). | Pass (deployment check) |
| **3.8 Privacy and compliance** | | | | |
| SEC-33 | Collect only account, delivery and order data | The User model holds only account fields; registration asks for email, phone and password; orders hold items, totals and the encrypted address. | SEC33DataMinimisationTests: the user model's stored fields and the registration fields match an exact allow-list. | Pass |
| SEC-34 | Registration links to a privacy notice | New /accounts/privacy/ page: what is collected, why, what is never collected, who sees it, and the user's rights. Linked from registration and the footer of every page. | SEC34PrivacyNoticeTests: registration links to the notice, and the notice covers what, why and rights. | Pass |
| SEC-35 | Users can have personal data corrected or deleted, except legally required order records | My account now lets users correct name, email and phone, and delete their account with password confirmation. Deletion erases contact details, disables sign-in and keeps orders and invoices linked to the anonymised row. | SEC35DataCorrectionAndDeletionTests: details are corrected; deletion needs the password, erases personal data, logs the user out, keeps orders and blocks sign-in. | Pass |
| **3.9 Third-party integrations and development practice** | | | | |
| SEC-36 | Integrations use authenticated, documented APIs over TLS | The carrier client refuses any URL that is not https://. Stripe uses a fixed https base URL with a Bearer key; the carrier sends a Bearer key; SMTP uses TLS by default; the inbound webhook is HMAC-signed. | SEC36SecureIntegrationsTests: Stripe and carrier requests are HTTPS and carry Authorization headers; an http:// carrier URL is refused without a network call. | Pass |
| SEC-37 | Secrets in environment configuration, never in the repository | Secret key, database password, Stripe, SMTP, field and backup keys are read from the environment; .env is git-ignored. | SEC37SecretsOutOfSourceTests: settings read each secret from os.environ; a scan of every tracked file finds no live keys, AWS keys, private keys or GitHub tokens, and .env is not tracked. | Pass |
| SEC-38 | Libraries checked for known vulnerabilities and updated | Pillow raised to >=13,<14 (13.0.0). The CI workflow gained a 'Dependency and static security scan' job that runs pip-audit on every push and pull request. | SEC38DependencyHygieneTests checks the CI step and the Pillow version. pip-audit now reports no known vulnerabilities (section 7.2). | Pass |
| SEC-39 | Security check in code review; unit tests cover the security rules | A pull request template with a SEC-39 security checklist; Bandit in CI; this suite of 98 tests, one class per requirement. | SEC39SecureDevelopmentTests: the template and the CI steps exist, and a meta-test fails if any SEC-1 to SEC-39 lacks a test class. | Pass (deployment check) |

## Confirmed values (requirements section 4)

| Item | Proposed | Implemented | Setting | Req |
| --- | --- | --- | --- | --- |
| Account lockout time after 3 failed logins | 15 minutes | 15 minutes | LOGIN_MAX_FAILURES=3, LOGIN_LOCKOUT_MINUTES=15 | SEC-3 |
| Password reset OTP / link validity | 10 minutes | 10 minutes (both) | MAX_OTP_LIFETIME, PASSWORD_RESET_TIMEOUT=600 | SEC-5 |
| OTP / reset requests per account | 5 per hour | 5 per hour | RATE_LIMITS['password_reset_account'] | SEC-6 |
| Session inactivity timeout | 30 minutes | 30 minutes | SESSION_COOKIE_AGE=1800, SESSION_SAVE_EVERY_REQUEST | SEC-8 |
| Security log retention | 90 days | 90 days | SECURITY_LOG_RETENTION_DAYS, DB trigger | SEC-32 |

## Deployment checks

| Req | Check |
| --- | --- |
| SEC-16 | Configure the web server or proxy for TLS 1.2 and 1.3 only, set DJANGO_FORCE_HTTPS=1, and make the proxy send X-Forwarded-Proto. Check with an SSL test (for example testssl.sh) once deployed. |
| SEC-30 | Behind a proxy, make sure REMOTE_ADDR is the real client address (for example gunicorn --forwarded-allow-ips), or every client shares one rate-limit bucket. |
| SEC-20 | Set BACKUP_ENCRYPTION_KEY, keep it apart from the backups, run encrypted_backup from cron as a dedicated operator account, and store copies where only that account and the database owner can read them. |
| SEC-32 | Run purge_security_events daily. If SECURITY_LOG_FILE is used, create the file owned by the service account with mode 0600. Do not give the application database role ownership of the trigger function. |
| SEC-39 | Turn on the branch ruleset on main with one required approving review and the two CI checks as required status checks. The README describes it, but it is not enforced on GitHub yet. |
| SEC-14 | Give every staff account an email address; without one an admin cannot receive the second-factor code. |

## Residual risks

- Email addresses stay in plain text so login by email works. SEC-17 names phone numbers and addresses, which are now encrypted; encrypting email would need the same digest approach as phone.
- The review content filter is a word and pattern list. It will miss some abuse and hold some harmless reviews; moderators should extend BLOCKED_TERMS as they see new patterns.
- The admin second factor is a code sent to the admin's email. It protects against a stolen password, but not against someone who also controls that inbox. An authenticator-app (TOTP) factor would be stronger.
- Rate limits are per client address. A distributed attack from many addresses is slowed by the per-identifier lockout and per-account reset cap, not stopped. A WAF or CDN in front of the site would add protection.
- TLS version, backup storage and branch protection are deployment settings. They are documented here but cannot be verified until the site and repository settings are configured.
