# Online Bookstore

Software engineering course project.

## Stack (decided in issue #21)

- Python 3 + Django (server-rendered templates)
- PostgreSQL (schema managed only through Django migrations)
- Custom user model (`accounts.User`), login by email or phone; passwords use Django's built-in hashing
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

## Tests

```
python -m coverage run manage.py test
python -m coverage report      # fails below 70%
```

The test database is created automatically, so the `bookstore` role needs `CREATEDB`.

## Schema

| App | Tables |
| --- | --- |
| accounts | `User` (email, optional unique phone, hashed password) |
| catalog | `Book` (title, author, ISBN, category, price, stock) |
| cart | `Cart` (one per user), `CartItem` |
| orders | `Order`, `OrderItem` (no card data is ever stored) |
| reviews | `Review` (1-5 rating, one per user per book) |
