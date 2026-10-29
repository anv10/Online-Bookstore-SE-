# Sprint 2 demo video (2 minutes): issue #32

Recording checklist and a timed script for the Sprint 2 deliverable. The video must show a working product and be uploaded to the repository.

## Before recording

1. Merge the Sprint 2 pull requests you want to show (cart #48, invoice #49, seller orders #54, TLS/encryption #46, checkout #9) so `main` contains them, then check out `main`.
2. Prepare the environment: PostgreSQL database, `.env` with `DJANGO_SECRET_KEY`, `DB_*`, and `PAYMENT_GATEWAY=sandbox`; then `python manage.py migrate`.
3. Seed demo data:
   - an admin account with `is_staff=True` and the `catalog.change_book` permission, plus a working SMTP sender for the moderation code;
   - a seller account with at least two approved listings, one of them with stock 1 to show the last-copy behaviour;
   - a buyer account with an empty cart.
4. Use a clean browser window at a readable zoom, close notifications, and hide any real API keys or personal data.
5. Rehearse once with a timer. Keep the recording at 1:55-2:00.

## Script

| Time | Screen | Say / do |
| --- | --- | --- |
| 0:00-0:10 | Landing page | "Online Bookstore, Sprint 2. Buyers check out and pay, sellers manage orders and admins moderate listings." |
| 0:10-0:30 | Discover page | Search "clean", apply a genre and price filter, open a book's details page and point out price, stock, seller and reviews. |
| 0:30-0:50 | Seller studio, then moderation | As the seller, open the listings page and show a pending listing. Switch to the admin, request and enter the email code, then approve the listing from the moderation queue and explain that the reason is recorded in the audit trail. |
| 0:50-1:10 | Book details and cart | As the buyer, add two copies, open the cart, change a quantity, show the recalculated total, then press "Proceed to checkout" and read out the items, tax, shipping and grand total. |
| 1:10-1:30 | Checkout | Enter the address, submit the declining sandbox card `4000 0000 0000 0002` and show that the cart survives. Then pay with `4242 4242 4242 4242`, any future expiry and any three digits. |
| 1:30-1:45 | Confirmation and invoice | Show order number, total and status Paid, open the invoice, and return to the book to point out the decremented stock. |
| 1:45-2:00 | Seller orders | As the seller, open the incoming orders for that order, mark it shipped, and close on the green CI run and the test/coverage summary. |

## After recording

1. Keep the file under about 100 MB and name it `Sprint2_Demo.mp4`.
2. Upload it to the repository (`Documents/`) or attach it to the Sprint 2 release if the file is too large for Git; link it from the README either way.
3. Add the link to issue #32 and close it.
4. Confirm the upload plays from a fresh browser session.
