# Password reset: issue #3

Implements FR-14. The login page links to `/accounts/password-reset/`, where the user enters their email or phone number.

## Workflow

1. The user submits their email or phone number. The reply is always the same page, whether or not an account matches.
2. If an active account with an email address matches, the email contains both a reset link and a six digit OTP. Suspended and removed accounts are skipped.
3. The link opens a page to choose a new password. The OTP can also be entered at `/accounts/password-reset/otp/` and then leads to the same page. It expires after ten minutes, allows five attempts and works once.
4. The new password must pass the same rules as registration (Django validators plus at least one letter and one digit).
5. After the change the user is sent to the login page. Every other session for the account stops working, because the session hash is derived from the password.

The link is built with Django's token generator. It works once, because setting the password changes the hash the token is made from, and it expires after `PASSWORD_RESET_TIMEOUT` (3600 seconds, set in `bookstore/settings.py`; change it there if operations need another value).

## Known limits

- Accounts without an email address get no message: there is no SMS gateway. Registration now requires an email, so this only affects accounts created directly in the database or admin.
- The request page has no rate limit yet. The OTP itself allows five attempts and expires after ten minutes.
- The email is sent during the request. If sending fails the error is logged and the user still sees the normal "check your email" page.

## Test-plan mapping

| Behaviour | Test |
| --- | --- |
| Link sent for email or phone | `test_password_reset.test_request_with_email_sends_link`, `test_request_with_phone_sends_link_to_account_email` |
| Same reply for unknown accounts | `test_password_reset.test_unknown_account_gets_same_reply_and_no_mail` |
| Suspended accounts excluded | `test_password_reset.test_suspended_account_gets_no_mail` |
| Single use | `test_password_reset.test_link_is_single_use`, `test_reset_otp.test_a_code_can_only_be_used_once` |
| Expiry | `test_password_reset.test_link_expires`, `test_reset_otp.test_an_expired_code_is_refused` |
| Strength rules | `test_password_reset.test_weak_password_is_rejected`, `test_password_without_digit_is_rejected`, `test_mismatch_is_rejected` |
| Old sessions logged out | `test_password_reset.test_old_sessions_are_logged_out_after_reset` |
| Wrong OTP refused | `test_reset_otp.test_the_wrong_code_is_refused_and_no_reset_happens` |
| OTP sets the new password | `test_reset_otp.test_the_new_password_is_saved_and_works_for_login` |
