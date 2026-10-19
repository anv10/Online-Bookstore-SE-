# Issue #4: search by title, author or ISBN

Assigned to kishansaaai. Implementation requires team review.

Case-insensitive partial title/author matching, exact ISBN, empty-query validation, no-result messages and nine-book pagination. Search results display catalogue cards; book-detail navigation belongs to teammate issue #6 and is intentionally not implemented here. Uses parameterised Django ORM and escaped templates.

Dependency: builds on PR #37 commit 38efd70. This feature does not merge or modify that teammate branch. DEFAULT_AUTO_FIELD is explicitly aligned with the existing BigAutoField migrations for Django 5.2 support.
