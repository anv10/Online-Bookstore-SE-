# Password reset: issue #3

Implements FR-14. The login page links to `/accounts/password-reset/`, where the user enters their email or phone number.

## Workflow

1. The user submits their email or phone number. The reply is always the same page, whether or not an account matches.
2. If an active account with an email address matches, a link is emailed to that address. Suspended and removed accounts are skipped.
3. The link opens a page to choose a new password. It must pass the same rules as registration (Django validators plus at least one letter and one digit).
4. After the change the user is sent to the login page. Every other session for the account stops working, because the session hash is derived from the password.

The link is built with Django's token generator. It works once, because setting the password changes the hash the token is made from, and it expires after `PASSWORD_RESET_TIMEOUT` (3600 seconds, set in `bookstore/settings.py`; change it there if operations need another value).

## Known limits

- Phone-only accounts get no message: there is no SMS gateway. The "email or phone" criterion is therefore met for accounts that have an email. Recorded as a deviation on issue #3.
- The request page has no rate limit yet.
- The email is sent during the request.

## Test-plan mapping

| Behaviour | Test in `accounts/tests/test_password_reset.py` |
| --- | --- |
| Link sent for email or phone | `test_request_with_email_sends_link`, `test_request_with_phone_sends_link_to_account_email` |
| Same reply for unknown accounts | `test_unknown_account_gets_same_reply_and_no_mail` |
| Suspended accounts excluded | `test_suspended_account_gets_no_mail` |
| Single use | `test_link_is_single_use` |
| Expiry | `test_link_expires` |
| Strength rules | `test_weak_password_is_rejected`, `test_password_without_digit_is_rejected`, `test_mismatch_is_rejected` |
| Old sessions logged out | `test_old_sessions_are_logged_out_after_reset` |
