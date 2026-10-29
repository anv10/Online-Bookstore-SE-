# Online Bookstore

Software engineering course project.

## Stack (decided in issue #21)

- Python 3 + Django (server-rendered templates)
- PostgreSQL (schema managed only through Django migrations)
- Custom user model (`accounts.User`), login by email or phone; passwords are hashed with Argon2
- One app per area: `accounts`, `catalog`, `cart`, `orders`, `reviews`
- Tests: Django test runner + `coverage` (70% gate, see `.coveragerc`)

## Local setup

1. Install Python 3.11+ and PostgreSQL 14+.
2. Create the database and role:
   ```
   psql -c "CREATE ROLE bookstore LOGIN CREATEDB PASSWORD 'choose-a-password'"
   psql -c "CREATE DATABASE bookstore OWNER bookstore"
   ```
3. Create a virtualenv and install dependencies:
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env`, fill in the values, and load it (`set -a; source .env; set +a`). Never commit `.env`.
5. Apply the schema: `python manage.py migrate`
6. Run the app: `python manage.py runserver`

## Security settings (NFR-6)

- Set `DJANGO_FORCE_HTTPS=1` in production: Django redirects HTTP to HTTPS, sends HSTS and marks cookies secure. TLS 1.2+ itself is configured on the web server or proxy in front of Django, which must send `X-Forwarded-Proto`.
- `Order.shipping_address` is encrypted at rest (Fernet). Set `FIELD_ENCRYPTION_KEY` to a key from `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If it is empty, a key is derived from `DJANGO_SECRET_KEY`. Do not change this key (or rotate the secret key while it is derived) once data exists, or stored addresses can no longer be decrypted (reading them raises an error instead of returning garbage). Migration `orders.0003` encrypts addresses that were saved before encryption existed.
- The secret key, database password and encryption key are read from environment variables only; `.env` is git-ignored.

## Tests

```
python -m coverage run manage.py test
python -m coverage report      # fails below 70%
```

The test database is created automatically, so the `bookstore` role needs `CREATEDB`.

## Schema

| App | Tables |
| --- | --- |
| accounts | `User` (email, optional unique phone, hashed password, suspension/removal timestamps), `AccountAction` (audit log) |
| catalog | `Book` (title, author, ISBN, category, price, stock) |
| cart | `Cart` (one per user), `CartItem` |
| orders | `Order`, `OrderItem` (no card data is ever stored) |
| reviews | `Review` (1-5 rating, one per user per book) |

## Continuous integration and review rules

The workflow in `.github/workflows/django-tests.yml` (check name: **PostgreSQL tests and coverage**) runs on every pull request and on every push to `main`. It:

1. installs the dependencies from `requirements.txt` on Python 3.12 with PostgreSQL 16;
2. runs `python manage.py check` and `python manage.py makemigrations --check --dry-run`, which fails if a model change has no migration;
3. applies the migrations and runs the test suite with `coverage`;
4. fails the build if total coverage is below **70%** (`coverage report --fail-under=70`).

`main` is protected by a branch ruleset: changes reach it only through a pull request, and each pull request needs **at least one approving review** from someone other than its author. The **PostgreSQL tests and coverage** check should also be marked as a required status check in that ruleset, so a pull request cannot be merged while it is red.

## Admin user account moderation

Account administrators use **Users** in the navigation to search accounts and
suspend or remove them with a required reason. Suspended and removed accounts
cannot log in, existing sessions stop working, and a seller's listings disappear
from the catalogue. Every action is recorded in an audit table; removal is soft
so order and review history stays intact. Access requires staff status and
`accounts.change_user`. See
[user account moderation](docs/sprint2/user-account-moderation.md) for the
workflow, test-plan mapping and remaining checks.

## Admin listing moderation

Moderators use `/moderation/` to review pending listings and approve, suspend or
remove them with a reason and an audit record. Access requires staff status,
`catalog.change_book`, and an email verification code. Configure the SMTP
variables in `.env.example` before use. See
[moderation setup and validation](docs/sprint2/admin-moderation.md) for provisioning,
security scope, test-plan mappings and remaining deployment checks.
