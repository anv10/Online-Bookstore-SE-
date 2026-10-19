# Issue #15: seller creates book listings

Assigned to kishansaaai. Implementation requires team review.

The add form accepts title, author, ISBN-10/13, genre, positive price, condition, non-negative stock, description and up to five PNG/JPEG images. Every uploaded image is decoded/verified, bounded to 2 MB and 20 megapixels; filenames are randomised. Both buyer-supplied owner IDs and approval states are ignored. New listings always start Pending approval and are excluded from catalogue search until approved. Public results also exclude inactive sellers. Seller permission is the existing Django `catalog.add_book` permission, granted by the team/admin to approved sellers, rather than a new account/role model that would conflict with teammate authentication work.

Multiple sellers can use the same ISBN. The Book row continues to represent one seller listing, with BookImage rows for its image gallery. Existing foundation Book rows have nullable seller for migration compatibility and remain non-public until assigned to an active seller and approved. This requires a catalogue migration; it does not modify the teammate's User model.

An ownership-scoped listing summary shows the created record and Pending status. Editing/deleting listings is teammate issue #16 and is not implemented. Django admin can change Book status for integration testing; the full moderation feature is later work. No authentication/register/detail/cart/checkout endpoints are added.

The login redirect points to `/accounts/login/`, which must be provided by teammate issue #2. Until that is merged, use a local administrator session to exercise the form; automated tests authenticate synthetic users directly. The fixture test that approves a row verifies publication after status change; it is not a claim that a full moderation workflow is finished.

Test evidence: 22 total tests pass with 98% application Python coverage on SQLite; excludes tests/migrations. PostgreSQL execution and remote CI remain unverified.
