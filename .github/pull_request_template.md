## What changed

## Requirement(s)

## Security check (SEC-39)

Tick each item or say why it does not apply.

- [ ] Every new view checks permissions on the server (login, role, and ownership of the object) (SEC-10 to SEC-13)
- [ ] User input is validated by a form on the server; no raw SQL or `|safe` / `mark_safe` on user content (SEC-25 to SEC-27)
- [ ] State-changing requests are POST with a CSRF token; nothing new is `csrf_exempt` without a signature check (SEC-28)
- [ ] No passwords, OTPs, tokens, card data or personal data in logs, URLs or error messages (SEC-18, SEC-19)
- [ ] No secrets in the code; new configuration is read from the environment and listed in `.env.example` (SEC-37)
- [ ] New dependencies pass `pip-audit` (SEC-38)
- [ ] Security-relevant behaviour is covered by tests in `security/tests/` or the app's tests (SEC-39)
- [ ] Security events are recorded with `security.events.record` where relevant (SEC-31)

## Tests
