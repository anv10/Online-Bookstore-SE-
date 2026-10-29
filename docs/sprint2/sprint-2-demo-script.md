# Sprint 2 demo video (2 minutes): issue #32

Recording checklist and a timed script for the Sprint 2 deliverable. The video must show a working product and be uploaded to the repository.

## Before recording

1. Merge the Sprint 2 pull requests you want to show (cart #48, invoice #49, seller orders #54, TLS/encryption #46, checkout #9, reviews #18, account moderation #20, support #30) so `main` contains them, then check out `main`.
2. Prepare the environment: PostgreSQL database, `.env` with `DJANGO_SECRET_KEY`, `DB_*`, `FIELD_ENCRYPTION_KEY`, `SUPPORT_EMAIL`, and `PAYMENT_GATEWAY=sandbox`; then `python manage.py migrate`.
3. Seed demo data:
   - an admin account with `is_staff=True`, `accounts.change_user` and `catalog.change_book` (staff status plus both permissions; a superuser also works);
   - a working SMTP sender if you want to show the moderation email code (otherwise skip that scene);
   - a seller account with at least two approved listings, one of them with stock 1 to show the last-copy behaviour;
   - a buyer account with an empty cart and one delivered order for the book that will be reviewed;
   - a second ordinary account to suspend in the account-moderation scene.
4. Use a clean browser window at a readable zoom, close notifications, and hide real API keys, email addresses or personal data.
5. Rehearse once with a timer. Keep the recording at 1:55-2:00.

## Script

| Time | Screen | Say / do |
| --- | --- | --- |
| 0:00-0:10 | Landing page and footer | "Online Bookstore, Sprint 2. Buyers check out and pay, sellers fulfil orders, admins moderate the platform, and every page links to support." |
| 0:10-0:25 | Discover page and book details | Search "clean", apply a genre and price filter, open a book and point out price, stock, seller and the existing average rating. |
| 0:25-0:40 | Seller listings and moderation | As the seller, show a pending listing. As the admin, approve it from the moderation queue (email code if configured) and explain that the reason is audited. |
| 0:40-0:55 | Book details and cart | As the buyer, add two copies, open the cart, change a quantity, show the recalculated total, then open checkout and read out the items, tax, shipping and grand total. |
| 0:55-1:10 | Checkout | Enter the address, submit the declining sandbox card `4000 0000 0000 0002` and show that the cart survives. Pay with `4242 4242 4242 4242`, any future expiry and any three digits. |
| 1:10-1:20 | Confirmation and invoice | Show the order number, total and status Paid, open the invoice, and return to the book to point out the decremented stock. |
| 1:20-1:30 | Seller orders | As the seller, open the incoming order, mark it shipped, then mark it delivered; point out that the buyer can now review. |
| 1:30-1:40 | Reviews | As the buyer, open the delivered book, submit a 5-star review with text, and show the new average and review count on the page. |
| 1:40-1:50 | Admin account moderation | As the admin, open **Users**, search for the ordinary account, suspend it with a reason, and show the audit entry. Point out that login is blocked and the seller's listings disappear. |
| 1:50-2:00 | Support and CI | Open **Customer support** from the footer, show the email channel and 24-hour target, then close on the green CI run and the coverage summary. |

## After recording

1. Keep the file under about 100 MB and name it `Sprint2_Demo.mp4`.
2. Upload it to the repository (`Documents/`) or attach it to the Sprint 2 release if the file is too large for Git; link it from the README either way.
3. Add the link to issue #32 and close it.
4. Confirm the upload plays from a fresh browser session.

## If a scene is not merged yet

Record only the features present on `main`. Do not claim a feature in narration if its pull request is still open. The acceptance criterion for #32 is a working product; it is better to show fewer features working than to show a branch that is not merged.
