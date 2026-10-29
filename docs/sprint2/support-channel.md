# Customer support channel: issue #30

Implements NFR-12 with an email support channel that is reachable from every page.

## What is available

- A **Customer support** link in the footer of every rendered page, including the catalogue, book details, cart, orders, account, login, register and support pages.
- `/support/` explains the email channel, shows the configured address and lists common questions for buyers and sellers.
- The address comes from `SUPPORT_EMAIL` (see `.env.example`). The committed default is a placeholder; set it to a monitored inbox in each environment.
- The page states the 24-hour first-response target and asks users to include their order number and account identifier so requests can be actioned quickly.

## Configuration

```
SUPPORT_EMAIL=support@your-domain.example
```

No application secrets or customer messages are stored by this feature. Mail is handled by the team's external support inbox, so the response process and retention policy live outside the codebase.

## Validation

`bookstore/tests/test_support.py` checks that the page is public, renders the configured address and `mailto:` link, states the 24-hour target, avoids exposing account data, and that the footer link appears on both public and authenticated pages.

## Deviations and remaining checks

- NFR-12 allows chat **or** email; this implements email only. There is no live-chat widget or ticketing integration.
- The 24-hour response time is a published service target, not an automated guarantee. Real monitoring of the inbox and response times is an operational responsibility.
- The support address must be configured before deployment; the sample value is intentionally not a real inbox.
- Browser, mobile and deployment checks remain part of the Sprint 2 validation and review process.
- AI-assisted implementation. Assigned team member submission, human review and approval remain separate steps.
