# Kishan's assigned Sprint 1 work

GitHub account: **kishansaaai**. Scope is only #4, #5 and #15. Future-sprint or unscheduled assignments (#9, #12, #18, #19, #24, #27, #30, #32) are not claimed complete.

| Issue | Implemented feature | Local status |
|---|---|---|
| #4 | Partial case-insensitive title/author search, exact ISBN, empty/no-result states, pagination | Implemented and tested |
| #5 | Multiple genre selection, inclusive price boundaries, combined keyword filters, clear/reset and query-preserving pagination | Implemented and tested |
| #15 | Permission-protected seller creation, validated data and multiple images, pending approval, owner-scoped summary, approved-only public visibility | Implemented and tested |

No teammate registration/login, book-detail page, listing edit/removal, CI workflow or video deliverable is included as new work in this package. The original foundation includes unimplemented schema/apps for later work. The earlier whole-team ZIP is superseded for Kishan's scope by this focused package.

## Integration and submission

The prerequisite is teammate PR #37 at commit `38efd70b1adc8b27a76d31bc084cd063c319caa5`. The separate three patches apply in order to that exact foundation, once it is reviewed/merged (or to a local checkout of its branch for testing). Back up existing work and check for overlaps before applying.

The first patch builds search and shared catalogue styling; the second layers filters; the third layers seller creation and publication rules. Each patch contains only its feature and supporting wiring/tests. Existing SRS/security/use-case/test-plan files are unchanged.

Submission status on 19 October 2026: the assigned member pushed the three feature branches. PR creation, review and integration are pending. The original issue assignees are unchanged. Search builds on teammate PR #37; filters build on search; listing creation builds on filters.

## Local setup

Python 3.11+ is the foundation baseline; local verification used Python 3.12 and Django 5.2.18. PostgreSQL remains the default settings profile. Install dependencies and load database/secrets environment variables as described in the repository README. Never commit a real `.env`.

For an explicitly offline preview, Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DJANGO_SETTINGS_MODULE = 'bookstore.local_settings'
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `/admin/` and log in as the local administrator, then visit `/seller/new/` to create a listing. It appears on `/seller/` as Pending approval. In `/admin/catalog/book/`, edit the record and set status Approved. It then appears on `/`. This is an integration demonstration, not a substitute for normal seller login from teammate issue #2.

Linux shell uses `python3 -m venv .venv`, `source .venv/bin/activate`, and `export DJANGO_SETTINGS_MODULE=bookstore.local_settings`; the remaining commands are the same.

Do not deploy the offline profile. An administrator/superuser has the add-book permission automatically; ordinary approved sellers need the `catalog.add_book` permission assigned by the team's account-management process. No buyer can self-grant this through the form.

## Validation

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python -m coverage run manage.py test
python -m coverage report --fail-under=70
```

Select either local settings above or configured PostgreSQL settings. Local results: **22 tests passed; 98% Python coverage** (tests and migrations omitted). Search/filter tests passed separately before the seller change (13 tests at #4, 16 at #5). The test suite covers ownership spoofing, CSRF, permission denial, unpublished/inactive sellers, image rejection, multi-image persistence and subsequent publication.

Not verified: PostgreSQL execution, four-browser behaviour, 500-user load, TLS/encryption at rest and remote CI. Human review and integration remain required. The implementation follows the submitted normal behaviour; publication waits for approval, resolving the test-plan inconsistency that expected immediate visibility.
